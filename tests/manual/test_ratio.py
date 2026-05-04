import ctypes, subprocess, time
class Pnt(ctypes.Structure): _fields_=[('x', ctypes.c_long), ('y', ctypes.c_long)]
pt=Pnt()
ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
startX=pt.x
p=subprocess.Popen(['D:/02_Workspace/C/mouse/lghub_mouse_tool/build/lghub_siminput_controller.exe', '--quiet', 'stream'], stdin=subprocess.PIPE, text=True)
time.sleep(0.5)
p.stdin.write('move 100 0\n')
p.stdin.flush()
time.sleep(0.5)
ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
print(f'Requested: 100, Actual: {pt.x - startX}')
p.terminate()