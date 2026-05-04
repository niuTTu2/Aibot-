#include <vector>
#include <cmath>
#include <algorithm>
#include <cstdint>

#if defined(_WIN32)
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

extern "C" {

struct Box {
    float x1, y1, x2, y2;
    float conf;
    int class_id;
};

// Computes the Intersection over Union (IoU) of two bounding boxes
static inline float compute_iou(const Box& a, const Box& b) {
    float xx1 = std::max(a.x1, b.x1);
    float yy1 = std::max(a.y1, b.y1);
    float xx2 = std::min(a.x2, b.x2);
    float yy2 = std::min(a.y2, b.y2);

    float w = std::max(0.0f, xx2 - xx1);
    float h = std::max(0.0f, yy2 - yy1);
    float inter = w * h;
    
    if (inter == 0.0f) {
        return 0.0f;
    }

    float area_a = (a.x2 - a.x1) * (a.y2 - a.y1);
    float area_b = (b.x2 - b.x1) * (b.y2 - b.y1);

    return inter / (area_a + area_b - inter);
}

// Entry point from Python ctypes
// - preds_ptr: Float array of shape [1, 84, 8400] flattened
// - num_classes: Example 80 (since 84 = 4 bounding box + 80 classes)
// - num_anchors: Example 8400 columns
// - conf_thres: Ignore predictions below this confidence score
// - iou_thres: Non-maximum suppression threshold
// - out_boxes: Pointer to pre-allocated float array where results will be written (stride: 6 floats per detection: x1, y1, x2, y2, conf, class_id)
// - max_out: Capacity of out_boxes in number of detections
// Returns: Number of detections written
EXPORT int run_yolov8_nms(const float* preds_ptr, int num_classes, int num_anchors, 
                          float conf_thres, float iou_thres, 
                          float* out_boxes, int max_out) {
    if (preds_ptr == nullptr || out_boxes == nullptr) return 0;
    if (num_classes <= 0 || num_anchors <= 0 || max_out <= 0) return 0;
    
    std::vector<Box> candidates;
    candidates.reserve(300);

    const int row_stride = num_anchors;
    // Iterate over all 8400 anchors (columns)
    for (int col = 0; col < num_anchors; ++col) {
        float max_conf = 0.0f;
        int best_class_id = -1;

        // The first 4 rows are box coordinates (cx, cy, w, h)
        // Rows 4 to 83 are class probabilities
        for (int c = 0; c < num_classes; ++c) {
            float conf = preds_ptr[(4 + c) * row_stride + col];
            if (conf > max_conf) {
                max_conf = conf;
                best_class_id = c;
            }
        }

        // If it passes threshold, decode the box
        if (max_conf >= conf_thres) {
            float cx = preds_ptr[0 * row_stride + col];
            float cy = preds_ptr[1 * row_stride + col];
            float w  = preds_ptr[2 * row_stride + col];
            float h  = preds_ptr[3 * row_stride + col];

            Box box;
            box.x1 = cx - w / 2.0f;
            box.y1 = cy - h / 2.0f;
            box.x2 = cx + w / 2.0f;
            box.y2 = cy + h / 2.0f;
            box.conf = max_conf;
            box.class_id = best_class_id;

            candidates.push_back(box);
        }
    }

    if (candidates.empty()) {
        return 0;
    }

    // Sort heavily by confidence (descending)
    std::sort(candidates.begin(), candidates.end(), [](const Box& a, const Box& b){
        return a.conf > b.conf;
    });

    // NMS
    std::vector<bool> suppressed(candidates.size(), false);
    int count = 0;

    for (size_t i = 0; i < candidates.size(); ++i) {
        if (suppressed[i]) continue;
        
        // Save to output
        if (count >= max_out) break;

        const Box& best = candidates[i];
        out_boxes[count * 6 + 0] = best.x1;
        out_boxes[count * 6 + 1] = best.y1;
        out_boxes[count * 6 + 2] = best.x2;
        out_boxes[count * 6 + 3] = best.y2;
        out_boxes[count * 6 + 4] = best.conf;
        out_boxes[count * 6 + 5] = static_cast<float>(best.class_id);
        count++;

        // Suppress overlaps for following boxes (only check same class, or independent based on standard YOLO NMS logic -- usually we suppress across all classes if we only care about overlap, but class-specific NMS is standard)
        for (size_t j = i + 1; j < candidates.size(); ++j) {
            if (!suppressed[j] && candidates[j].class_id == best.class_id) {
                if (compute_iou(best, candidates[j]) > iou_thres) {
                    suppressed[j] = true;
                }
            }
        }
    }

    return count;
}

} // extern "C"
