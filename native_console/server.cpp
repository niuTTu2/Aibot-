#define WIN32_LEAN_AND_MEAN
#define NOMINMAX

#include <windows.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <shellapi.h>
#include <commdlg.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <mutex>
#include <regex>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#pragma comment(lib, "Ws2_32.lib")
#pragma comment(lib, "Shell32.lib")
#pragma comment(lib, "Comdlg32.lib")

namespace fs = std::filesystem;

struct Request {
    std::string method;
    std::string path;
    std::string query;
    std::map<std::string, std::string> headers;
    std::string body;
};

struct Metrics {
    std::string capture_ms;
    std::string inference_ms;
    std::string total_ms;
    std::string fps;
};

struct ProcessState {
    std::mutex mutex;
    HANDLE process = nullptr;
    DWORD process_id = 0;
    bool running = false;
    Metrics metrics;
    std::vector<std::string> logs;
};

static fs::path g_root;
static int g_port = 8765;
static ProcessState g_state;

std::wstring widen(const std::string& text) {
    if (text.empty()) return L"";
    int size = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0);
    std::wstring result(size, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), size);
    return result;
}

std::string narrow(const std::wstring& text) {
    if (text.empty()) return "";
    int size = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string result(size, '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), result.data(), size, nullptr, nullptr);
    return result;
}

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (unsigned char c : value) {
        switch (c) {
            case '"': out << "\\\""; break;
            case '\\': out << "\\\\"; break;
            case '\b': out << "\\b"; break;
            case '\f': out << "\\f"; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default:
                if (c < 0x20) {
                    out << "\\u";
                    const char* hex = "0123456789abcdef";
                    out << "00" << hex[(c >> 4) & 0xf] << hex[c & 0xf];
                } else {
                    out << c;
                }
        }
    }
    return out.str();
}

std::string url_decode(const std::string& input) {
    std::string result;
    for (size_t i = 0; i < input.size(); ++i) {
        if (input[i] == '%' && i + 2 < input.size()) {
            std::string hex = input.substr(i + 1, 2);
            char decoded = static_cast<char>(std::strtol(hex.c_str(), nullptr, 16));
            result.push_back(decoded);
            i += 2;
        } else if (input[i] == '+') {
            result.push_back(' ');
        } else {
            result.push_back(input[i]);
        }
    }
    return result;
}

std::map<std::string, std::string> parse_query(const std::string& query) {
    std::map<std::string, std::string> values;
    size_t start = 0;
    while (start < query.size()) {
        size_t amp = query.find('&', start);
        std::string item = query.substr(start, amp == std::string::npos ? std::string::npos : amp - start);
        size_t eq = item.find('=');
        if (eq != std::string::npos) {
            values[url_decode(item.substr(0, eq))] = url_decode(item.substr(eq + 1));
        }
        if (amp == std::string::npos) break;
        start = amp + 1;
    }
    return values;
}

std::string read_file(const fs::path& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file) return "";
    std::ostringstream buffer;
    buffer << file.rdbuf();
    return buffer.str();
}

bool write_file(const fs::path& path, const std::string& body) {
    fs::create_directories(path.parent_path());
    std::ofstream file(path, std::ios::binary);
    if (!file) return false;
    file.write(body.data(), static_cast<std::streamsize>(body.size()));
    return true;
}

std::wstring quote_arg(const std::wstring& value) {
    std::wstring escaped = L"\"";
    for (wchar_t c : value) {
        if (c == L'"') escaped += L"\\\"";
        else escaped += c;
    }
    escaped += L"\"";
    return escaped;
}

fs::path config_path() {
    return g_root / ".runtime" / "web-console-config.json";
}

std::wstring find_python() {
    // Prefer project venv first
    fs::path venv_python = g_root / L".venv" / L"Scripts" / L"python.exe";
    if (fs::exists(venv_python)) return venv_python.wstring();

    fs::path preferred = L"D:\\06_Environment\\python\\python.exe";
    if (fs::exists(preferred)) return preferred.wstring();

    wchar_t buffer[MAX_PATH] = {};
    DWORD found = SearchPathW(nullptr, L"python.exe", nullptr, MAX_PATH, buffer, nullptr);
    if (found > 0 && found < MAX_PATH) return buffer;

    wchar_t user_profile[MAX_PATH] = {};
    DWORD profile_len = GetEnvironmentVariableW(L"USERPROFILE", user_profile, MAX_PATH);
    if (profile_len > 0 && profile_len < MAX_PATH) {
        fs::path app_python = fs::path(user_profile) / "AppData" / "Local" / "Python" / "pythoncore-3.14-64" / "python.exe";
        if (fs::exists(app_python)) return app_python.wstring();
    }
    return L"python";
}

void inject_cudnn_path() {
    // Inject cuDNN 9 path for CUDA 12.x so onnxruntime-gpu can find cudnn64_9.dll
    const wchar_t* cudnn_dir = L"C:\\Program Files\\NVIDIA\\CUDNN\\v9.21\\bin\\12.9\\x64";
    wchar_t current_path[32767] = {};
    GetEnvironmentVariableW(L"PATH", current_path, 32767);
    std::wstring new_path = std::wstring(cudnn_dir) + L";" + current_path;
    SetEnvironmentVariableW(L"PATH", new_path.c_str());
}

void append_log(const std::string& text) {
    std::lock_guard<std::mutex> lock(g_state.mutex);
    std::stringstream stream(text);
    std::string line;
    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        if (line.empty()) continue;
        g_state.logs.push_back(line);
        if (g_state.logs.size() > 600) g_state.logs.erase(g_state.logs.begin(), g_state.logs.begin() + 100);

        // Fallback or backup logic for standard metrics through stdout, 
        // though UDP will be the primary low-latency metric updater
        std::smatch match;
        std::regex metric_regex(R"(METRICS .*capture_ms=([0-9.]+).*inference_ms=([0-9.]+).*total_ms=([0-9.]+).*fps=([0-9.]+))");
        if (std::regex_search(line, match, metric_regex)) {
            g_state.metrics.capture_ms = match[1].str();
            g_state.metrics.inference_ms = match[2].str();
            g_state.metrics.total_ms = match[3].str();
            g_state.metrics.fps = match[4].str();
        }
    }
}

// v2 IPC: UDP receiver thread logic 
#pragma comment(lib, "ws2_32.lib")
void start_udp_listener() {
    std::thread([]() {
        WSADATA wsaData;
        WSAStartup(MAKEWORD(2, 2), &wsaData);

        SOCKET sock = socket(AF_INET, SOCK_DGRAM, 0);
        sockaddr_in serverAddr{};
        serverAddr.sin_family = AF_INET;
        serverAddr.sin_port = htons(8766);
        serverAddr.sin_addr.s_addr = inet_addr("127.0.0.1");

        bind(sock, (SOCKADDR*)&serverAddr, sizeof(serverAddr));

        char buffer[1024];
        while (true) {
            int bytesReceived = recvfrom(sock, buffer, sizeof(buffer) - 1, 0, nullptr, nullptr);
            if (bytesReceived > 0) {
                buffer[bytesReceived] = '\0';
                std::string line(buffer);
                
                std::smatch match;
                std::regex metric_regex(R"(METRICS .*capture_ms=([0-9.]+).*inference_ms=([0-9.]+).*total_ms=([0-9.]+).*fps=([0-9.]+))");
                if (std::regex_search(line, match, metric_regex)) {
                    std::lock_guard<std::mutex> lock(g_state.mutex);
                    g_state.metrics.capture_ms = match[1].str();
                    g_state.metrics.inference_ms = match[2].str();
                    g_state.metrics.total_ms = match[3].str();
                    g_state.metrics.fps = match[4].str();
                }
            }
        }
    }).detach();
}

bool start_process(const std::wstring& command_line) {
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        if (g_state.running) return false;
    }

    SECURITY_ATTRIBUTES security{};
    security.nLength = sizeof(security);
    security.bInheritHandle = TRUE;

    HANDLE read_pipe = nullptr;
    HANDLE write_pipe = nullptr;
    if (!CreatePipe(&read_pipe, &write_pipe, &security, 0)) return false;
    SetHandleInformation(read_pipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdOutput = write_pipe;
    startup.hStdError = write_pipe;
    startup.hStdInput = GetStdHandle(STD_INPUT_HANDLE);

    PROCESS_INFORMATION process_info{};
    std::wstring mutable_command = command_line;
    BOOL ok = CreateProcessW(
        nullptr,
        mutable_command.data(),
        nullptr,
        nullptr,
        TRUE,
        CREATE_NO_WINDOW,
        nullptr,
        g_root.wstring().c_str(),
        &startup,
        &process_info
    );
    CloseHandle(write_pipe);
    if (!ok) {
        CloseHandle(read_pipe);
        return false;
    }

    CloseHandle(process_info.hThread);
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        g_state.process = process_info.hProcess;
        g_state.process_id = process_info.dwProcessId;
        g_state.running = true;
        g_state.metrics = {};
        g_state.logs.clear();
    }
    append_log("Process started.");

    std::thread([read_pipe, process = process_info.hProcess]() {
        char buffer[4096];
        DWORD bytes_read = 0;
        while (ReadFile(read_pipe, buffer, sizeof(buffer) - 1, &bytes_read, nullptr) && bytes_read > 0) {
            buffer[bytes_read] = '\0';
            append_log(std::string(buffer, bytes_read));
        }
        WaitForSingleObject(process, INFINITE);
        DWORD exit_code = 0;
        GetExitCodeProcess(process, &exit_code);
        CloseHandle(read_pipe);
        {
            std::lock_guard<std::mutex> lock(g_state.mutex);
            g_state.running = false;
            g_state.process = nullptr;
            g_state.process_id = 0;
        }
        append_log("Process exited with code " + std::to_string(exit_code) + ".");
        CloseHandle(process);
    }).detach();

    return true;
}

void stop_process() {
    HANDLE process = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_state.mutex);
        process = g_state.process;
    }
    if (process) TerminateProcess(process, 0);
}

std::string run_capture(const std::wstring& command_line) {
    SECURITY_ATTRIBUTES security{};
    security.nLength = sizeof(security);
    security.bInheritHandle = TRUE;

    HANDLE read_pipe = nullptr;
    HANDLE write_pipe = nullptr;
    if (!CreatePipe(&read_pipe, &write_pipe, &security, 0)) return "{\"ok\":false,\"error\":\"pipe failed\"}";
    SetHandleInformation(read_pipe, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW startup{};
    startup.cb = sizeof(startup);
    startup.dwFlags = STARTF_USESTDHANDLES;
    startup.hStdOutput = write_pipe;
    startup.hStdError = write_pipe;

    PROCESS_INFORMATION process_info{};
    std::wstring mutable_command = command_line;
    BOOL ok = CreateProcessW(nullptr, mutable_command.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, g_root.wstring().c_str(), &startup, &process_info);
    CloseHandle(write_pipe);
    if (!ok) {
        CloseHandle(read_pipe);
        return "{\"ok\":false,\"error\":\"process failed\"}";
    }
    CloseHandle(process_info.hThread);

    std::string output;
    char buffer[4096];
    DWORD bytes_read = 0;
    while (ReadFile(read_pipe, buffer, sizeof(buffer), &bytes_read, nullptr) && bytes_read > 0) {
        output.append(buffer, buffer + bytes_read);
    }
    WaitForSingleObject(process_info.hProcess, INFINITE);
    CloseHandle(read_pipe);
    CloseHandle(process_info.hProcess);
    return output.empty() ? "{\"ok\":false,\"error\":\"empty output\"}" : output;
}

std::string status_json() {
    std::lock_guard<std::mutex> lock(g_state.mutex);
    std::ostringstream out;
    out << "{\"ok\":true,\"running\":" << (g_state.running ? "true" : "false") << ",\"metrics\":{";
    out << "\"capture_ms\":\"" << json_escape(g_state.metrics.capture_ms) << "\",";
    out << "\"inference_ms\":\"" << json_escape(g_state.metrics.inference_ms) << "\",";
    out << "\"total_ms\":\"" << json_escape(g_state.metrics.total_ms) << "\",";
    out << "\"fps\":\"" << json_escape(g_state.metrics.fps) << "\"},\"logs\":[";
    size_t start = g_state.logs.size() > 300 ? g_state.logs.size() - 300 : 0;
    for (size_t i = start; i < g_state.logs.size(); ++i) {
        if (i != start) out << ",";
        out << "\"" << json_escape(g_state.logs[i]) << "\"";
    }
    out << "]}";
    return out.str();
}

std::string default_config_json() {
    return R"({"capture":{"source":"dxgi","monitor_index":0,"device_index":0,"width":1920,"height":1080,"crop_width":0,"crop_height":0,"fps":60,"region":null},"model":{"path":"models/sample/yolov8n.onnx","imgsz":640,"conf":0.35,"iou":0.45,"device":null},"target":{"class_names":[],"prefer_center":true,"aim_offset_x":0.5,"aim_offset_y":0.5,"max_distance_px":900},"mouse":{"enabled":true,"hold_to_move":true,"backend":"sendinput","movement_mode":"adaptive","lghub_tool_path":"D:\\02_Workspace\\C\\mouse\\lghub_mouse_tool\\build\\lghub_siminput_controller.exe","lghub_strict":false,"lghub_delay_ms":0,"lghub_flush_interval_ms":8,"enable_keys":[6],"sensitivity":0.5,"smoothing":0.55,"deadzone_px":1,"min_step_px":1,"max_step_px":24,"max_step_boost":1.18,"sticky_radius_px":95,"sticky_strength":1.75,"pressure_strength":0.55,"pressure_cap":2.2,"micro_accel":true,"prediction_ms":28,"velocity_assist":0.45,"fast_boost":1.35,"trigger_enabled":false,"triggers":[],"kp":0.66,"kp_min":0.22,"kp_curve":0.62,"kd":0,"kd_max_ratio":0,"kalman_process_noise":3.5,"kalman_measure_noise":5.0,"kalman_gate_sigma":2.5,"lock_target":true,"lock_miss_frames":2,"weapon_switch_mode":"cycle","weapon_next_keys":[5],"weapon_prev_keys":[]},"runtime":{"preview":true,"preview_scale":0.5,"preview_initial_width":1920,"preview_initial_height":1080,"print_fps":true,"quit_key":"q"}})";
}

std::string config_json() {
    std::string saved = read_file(config_path());
    if (saved.empty()) saved = default_config_json();
    return "{\"ok\":true,\"config\":" + saved + "}";
}

std::string browse_model_json() {
    wchar_t file_name[4096] = {};
    OPENFILENAMEW ofn{};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = nullptr;
    ofn.lpstrFilter = L"YOLO Models\0*.pt;*.onnx;*.engine;*.trt;*.rtr\0All Files\0*.*\0";
    ofn.lpstrFile = file_name;
    ofn.nMaxFile = 4096;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
    if (!GetOpenFileNameW(&ofn)) return "{\"ok\":true,\"path\":\"\"}";
    return "{\"ok\":true,\"path\":\"" + json_escape(narrow(file_name)) + "\"}";
}

std::string model_info_json(const std::string& model_path) {
    std::wstring python = find_python();
    fs::path script = g_root / "scripts" / "model_info_cli.py";
    std::wstring command = quote_arg(python) + L" " + quote_arg(script.wstring()) + L" " + quote_arg(widen(model_path));
    return run_capture(command);
}

std::string devices_json() {
    std::wstring python = find_python();
    fs::path script = g_root / "scripts" / "device_info_cli.py";
    std::wstring command = quote_arg(python) + L" " + quote_arg(script.wstring());
    return run_capture(command);
}

std::string mouse_test_json(const std::string& backend, const std::string& tool_path, const std::string& strict, const std::string& delay_ms) {
    std::string selected_backend = backend.empty() ? "sendinput" : backend;
    append_log("MOUSE_STATUS state=test_requested source=browser backend=" + selected_backend);
    if (selected_backend != "sendinput" && selected_backend != "lghub_siminput") {
        append_log("MOUSE_STATUS state=backend_unavailable source=browser backend=" + selected_backend + " backend_ready=false test_skipped=true");
        return "{\"ok\":true,\"skipped\":true,\"backend\":\"" + json_escape(selected_backend) + "\",\"message\":\"selected mouse backend is not implemented; movement test skipped\"}";
    }
    append_log("MOUSE_CMD type=test_move backend=" + selected_backend + " circles=3 overlay=true");
    std::wstring python = find_python();
    fs::path script = g_root / "scripts" / "mouse_test_cli.py";
    std::wstring command = quote_arg(python) + L" " + quote_arg(script.wstring()) + L" --backend " + quote_arg(widen(selected_backend));
    if (selected_backend == "lghub_siminput") {
        if (!tool_path.empty()) command += L" --tool " + quote_arg(widen(tool_path));
        if (strict == "true" || strict == "1") command += L" --strict";
        if (!delay_ms.empty()) command += L" --delay " + quote_arg(widen(delay_ms));
    }
    std::string result = run_capture(command);
    append_log("MOUSE_STATUS state=test_finished source=browser backend=" + selected_backend);
    return result;
}

std::string mime_type(const std::string& path) {
    auto ends_with = [](const std::string& value, const std::string& suffix) {
        return value.size() >= suffix.size() && value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
    };
    if (ends_with(path, ".css")) return "text/css; charset=utf-8";
    if (ends_with(path, ".js")) return "application/javascript; charset=utf-8";
    if (ends_with(path, ".html")) return "text/html; charset=utf-8";
    return "text/plain; charset=utf-8";
}

bool send_all(SOCKET socket, const std::string& data) {
    size_t sent_total = 0;
    while (sent_total < data.size()) {
        int sent = send(socket, data.data() + sent_total, static_cast<int>(data.size() - sent_total), 0);
        if (sent <= 0) return false;
        sent_total += static_cast<size_t>(sent);
    }
    return true;
}

void send_response(SOCKET socket, int code, const std::string& content_type, const std::string& body) {
    std::string reason = code == 200 ? "OK" : code == 404 ? "Not Found" : "Error";
    std::ostringstream response;
    response << "HTTP/1.1 " << code << " " << reason << "\r\n";
    response << "Content-Type: " << content_type << "\r\n";
    response << "Content-Length: " << body.size() << "\r\n";
    response << "Access-Control-Allow-Origin: *\r\n";
    response << "Connection: close\r\n\r\n";
    response << body;
    send_all(socket, response.str());
}

bool read_request(SOCKET socket, Request& request) {
    std::string data;
    char buffer[4096];
    while (data.find("\r\n\r\n") == std::string::npos) {
        int received = recv(socket, buffer, sizeof(buffer), 0);
        if (received <= 0) return false;
        data.append(buffer, buffer + received);
        if (data.size() > 1024 * 1024) return false;
    }

    size_t header_end = data.find("\r\n\r\n");
    std::string headers = data.substr(0, header_end);
    request.body = data.substr(header_end + 4);

    std::istringstream stream(headers);
    std::string line;
    std::getline(stream, line);
    if (!line.empty() && line.back() == '\r') line.pop_back();
    std::istringstream first(line);
    std::string target;
    first >> request.method >> target;
    size_t question = target.find('?');
    request.path = question == std::string::npos ? target : target.substr(0, question);
    request.query = question == std::string::npos ? "" : target.substr(question + 1);

    while (std::getline(stream, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t colon = line.find(':');
        if (colon == std::string::npos) continue;
        std::string key = line.substr(0, colon);
        std::string value = line.substr(colon + 1);
        while (!value.empty() && value.front() == ' ') value.erase(value.begin());
        std::transform(key.begin(), key.end(), key.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
        request.headers[key] = value;
    }

    size_t content_length = 0;
    if (request.headers.count("content-length")) content_length = static_cast<size_t>(std::stoul(request.headers["content-length"]));
    while (request.body.size() < content_length) {
        int received = recv(socket, buffer, sizeof(buffer), 0);
        if (received <= 0) return false;
        request.body.append(buffer, buffer + received);
    }
    if (request.body.size() > content_length) request.body.resize(content_length);
    return true;
}

void handle_request(SOCKET client) {
    Request request;
    if (!read_request(client, request)) {
        closesocket(client);
        return;
    }

    try {
        if (request.method == "GET" && (request.path == "/" || request.path == "/index.html")) {
            send_response(client, 200, "text/html; charset=utf-8", read_file(g_root / "web_console" / "index.html"));
        } else if (request.method == "GET" && (request.path == "/styles.css" || request.path == "/app.js")) {
            fs::path file = g_root / "web_console" / request.path.substr(1);
            send_response(client, 200, mime_type(request.path), read_file(file));
        } else if (request.method == "GET" && request.path == "/api/status") {
            send_response(client, 200, "application/json; charset=utf-8", status_json());
        } else if (request.method == "GET" && request.path == "/api/config") {
            send_response(client, 200, "application/json; charset=utf-8", config_json());
        } else if (request.method == "POST" && request.path == "/api/config") {
            write_file(config_path(), request.body);
            send_response(client, 200, "application/json; charset=utf-8", "{\"ok\":true}");
        } else if (request.method == "POST" && request.path == "/api/start") {
            if (!request.body.empty()) write_file(config_path(), request.body);
            std::wstring python = find_python();
            std::wstring command = quote_arg(python) + L" -u -m yolo_mouse_controller --config " + quote_arg(config_path().wstring());
            bool ok = start_process(command);
            send_response(client, ok ? 200 : 500, "application/json; charset=utf-8", ok ? "{\"ok\":true}" : "{\"ok\":false,\"error\":\"controller already running or failed to start\"}");
        } else if (request.method == "POST" && request.path == "/api/install") {
            std::wstring python = find_python();
            fs::path req = g_root / "requirements.txt";
            std::wstring command = quote_arg(python) + L" -m pip install -r " + quote_arg(req.wstring());
            bool ok = start_process(command);
            send_response(client, ok ? 200 : 500, "application/json; charset=utf-8", ok ? "{\"ok\":true}" : "{\"ok\":false,\"error\":\"another process is running\"}");
        } else if (request.method == "POST" && request.path == "/api/stop") {
            stop_process();
            send_response(client, 200, "application/json; charset=utf-8", "{\"ok\":true}");
        } else if (request.method == "POST" && request.path == "/api/clear-logs") {
            std::lock_guard<std::mutex> lock(g_state.mutex);
            g_state.logs.clear();
            send_response(client, 200, "application/json; charset=utf-8", "{\"ok\":true}");
        } else if (request.method == "GET" && request.path == "/api/browse-model") {
            send_response(client, 200, "application/json; charset=utf-8", browse_model_json());
        } else if (request.method == "GET" && request.path == "/api/model-info") {
            auto query = parse_query(request.query);
            send_response(client, 200, "application/json; charset=utf-8", model_info_json(query["path"]));
        } else if (request.method == "GET" && request.path == "/api/devices") {
            send_response(client, 200, "application/json; charset=utf-8", devices_json());
        } else if (request.method == "POST" && request.path == "/api/mouse-test") {
            auto query = parse_query(request.query);
            send_response(client, 200, "application/json; charset=utf-8", mouse_test_json(query["backend"], query["tool"], query["strict"], query["delay"]));
        } else {
            send_response(client, 404, "application/json; charset=utf-8", "{\"ok\":false,\"error\":\"not found\"}");
        }
    } catch (const std::exception& exc) {
        send_response(client, 500, "application/json; charset=utf-8", "{\"ok\":false,\"error\":\"" + json_escape(exc.what()) + "\"}");
    }
    closesocket(client);
}

void parse_args(int argc, char** argv) {
    g_root = fs::current_path();
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--root" && i + 1 < argc) {
            g_root = widen(argv[++i]);
        } else if (arg == "--port" && i + 1 < argc) {
            g_port = std::stoi(argv[++i]);
        }
    }
}

int main(int argc, char** argv) {
    parse_args(argc, argv);
    inject_cudnn_path();
    
    // v2 IPC UDP metrics listener
    start_udp_listener();

    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        std::cerr << "WSAStartup failed\n";
        return 1;
    }

    SOCKET server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (server == INVALID_SOCKET) return 1;

    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    address.sin_port = htons(static_cast<u_short>(g_port));

    int reuse = 1;
    setsockopt(server, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&reuse), sizeof(reuse));
    if (bind(server, reinterpret_cast<sockaddr*>(&address), sizeof(address)) == SOCKET_ERROR) {
        std::cerr << "Port bind failed\n";
        return 1;
    }
    if (listen(server, SOMAXCONN) == SOCKET_ERROR) return 1;

    std::wstring url = L"http://127.0.0.1:" + std::to_wstring(g_port) + L"/";
    ShellExecuteW(nullptr, L"open", url.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
    std::wcout << L"YOLO web console: " << url << L"\n";
    std::wcout << L"Project root: " << g_root.wstring() << L"\n";

    while (true) {
        SOCKET client = accept(server, nullptr, nullptr);
        if (client == INVALID_SOCKET) continue;
        std::thread(handle_request, client).detach();
    }

    closesocket(server);
    WSACleanup();
    return 0;
}

