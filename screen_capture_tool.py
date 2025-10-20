"""
Screen Capture Tool - ENHANCED VERSION
- ESC/Enter saves position to history
- PrtSc restores LAST position automatically
- Backspace goes to PREVIOUS capture
- Tab goes to NEXT capture
- NEW: History appends at end (no deletion of future history)
- Clean interface with solid black help background
- Ctrl+Shift+4 also triggers capture mode
"""

import tkinter as tk
from tkinter import filedialog
from PIL import ImageGrab, Image, ImageTk
from datetime import datetime
import os
from pynput import keyboard
import sys
import socket
import errno
import io
import ctypes
import signal

# Fix DPI scaling
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass


class SingleInstance:
    def __init__(self, port=19283):
        self.port = port
        self.socket = None
        
    def is_already_running(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.bind(('127.0.0.1', self.port))
            return False
        except socket.error as e:
            if e.errno == errno.EADDRINUSE:
                return True
            return False
    
    def signal_existing_instance(self):
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.connect(('127.0.0.1', self.port))
            client.send(b'ACTIVATE_CAPTURE')
            client.close()
            return True
        except:
            return False
    
    def start_listening(self, callback):
        if not self.socket:
            return None
        
        self.socket.listen(1)
        self.socket.settimeout(0.5)
        
        def check_for_signals():
            try:
                conn, addr = self.socket.accept()
                data = conn.recv(1024)
                if data == b'ACTIVATE_CAPTURE':
                    callback()
                conn.close()
            except socket.timeout:
                pass
            except:
                pass
        
        return check_for_signals
    
    def cleanup(self):
        if self.socket:
            try:
                self.socket.close()
            except:
                pass


class ScreenCaptureApp:
    def __init__(self):
        self.root = None
        self.canvas = None
        self.is_active = False
        self.capture_requested = False
        self.should_quit = False
        
        self.single_instance = SingleInstance()
        self.last_save_dir = os.path.join(os.path.expanduser('~'), 'Downloads')
        
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        
        self.bg_screenshot = None
        self.bg_photo = None
        self.bg_item = None
        self.dark_rects = []
        
        self.is_selecting = False
        self.is_resizing = False
        self.is_moving = False
        self.resize_mode = None
        self.region_selected = False
        self.resize_threshold = 10
        
        self.move_start_x = None
        self.move_start_y = None
        self.move_offset_x = None
        self.move_offset_y = None
        
        self.corner_texts = []
        self.size_texts = []
        
        self.magnifier_window = None
        self.magnifier_canvas = None
        self.magnifier_size = 180
        self.magnifier_zoom = 3
        
        self.socket_check_callback = None
        self.last_adjust_mode = 'inside'
        self.initial_dark_overlay = None
        
        # Capture history - PERSISTENT across sessions
        self.capture_history = []  # List of (x1, y1, x2, y2)
        self.capture_history_index = -1  # Current position in history
        
        # Toggle for showing/hiding coordinate and size info
        self.show_info = True
        
        # Help text display
        self.help_bg_rect = None
        self.help_text_item = None
        
        # Signal handler
        signal.signal(signal.SIGINT, self.signal_handler)
        
        self.setup_keyboard_listener()
    
    def signal_handler(self, sig, frame):
        self.should_quit = True
        if self.is_active:
            self.deactivate_capture_mode()
        self.single_instance.cleanup()
        sys.exit(0)
    
    def setup_keyboard_listener(self):
        def on_press(key):
            try:
                # Handle PrtSc
                if key == keyboard.Key.print_screen:
                    if not self.is_active:
                        self.capture_requested = True
                        if self.root and self.root.winfo_exists():
                            self.root.lift()
                            self.root.focus_force()
                    return
                
                # Handle Ctrl+C to quit
                if hasattr(key, 'char') and key.char == 'c':
                    if hasattr(self, '_ctrl_pressed') and self._ctrl_pressed:
                        self.should_quit = True
                        if self.is_active:
                            self.deactivate_capture_mode()
                    return
                
                # Handle Ctrl+Shift+4 using vk code
                if hasattr(key, 'vk') and key.vk == 52:  # VK code for '4' key is 52 (0x34)
                    if hasattr(self, '_ctrl_pressed') and self._ctrl_pressed and \
                       hasattr(self, '_shift_pressed') and self._shift_pressed:
                        if not self.is_active:
                            self.capture_requested = True
                            if self.root and self.root.winfo_exists():
                                self.root.lift()
                                self.root.focus_force()
                    return
                
            except AttributeError:
                pass
            except Exception as e:
                pass
            
            # Handle modifier keys
            if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                self._ctrl_pressed = True
            elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                self._shift_pressed = True
        
        def on_release(key):
            try:
                if key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r:
                    self._ctrl_pressed = False
                elif key == keyboard.Key.shift_l or key == keyboard.Key.shift_r:
                    self._shift_pressed = False
            except AttributeError:
                pass
        
        self._ctrl_pressed = False
        self._shift_pressed = False
        listener = keyboard.Listener(on_press=on_press, on_release=on_release, suppress=False)
        listener.daemon = True
        listener.start()
    
    def toggle_info_display(self, event=None):
        """Toggle coordinate and size info visibility with I key"""
        self.show_info = not self.show_info
        if self.start_x is not None and self.end_x is not None:
            self.update_display()
        return "break"
    
    def toggle_help_display(self, event=None):
        """Toggle help text display with H key"""
        if not self.canvas:
            return "break"
        
        if self.help_bg_rect:
            self.canvas.delete(self.help_bg_rect)
            self.canvas.delete(self.help_text_item)
            self.help_bg_rect = None
            self.help_text_item = None
        else:
            help_content = """Screen Capture Tool - Keyboard Shortcuts

Select Area: Click and drag
Move Selection: Click inside and drag
Resize: Click corners/edges and drag

Arrow Keys: Adjust selection
Backspace: Previous capture
Tab: Next capture
I: Toggle info display
H: Toggle this help
Enter: Save to file
ESC: Copy to clipboard
Ctrl+C: Quit
PrtSc or Ctrl+Shift+4: Start capture"""
            
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            help_x = screen_width // 2
            help_y = screen_height // 2
            
            bbox_padding = 20
            temp_text = self.canvas.create_text(
                help_x, help_y,
                text=help_content,
                fill='white',
                font=('Consolas', 12, 'bold'),
                justify='left'
            )
            bbox = self.canvas.bbox(temp_text)
            self.canvas.delete(temp_text)
            
            if bbox:
                self.help_bg_rect = self.canvas.create_rectangle(
                    bbox[0] - bbox_padding,
                    bbox[1] - bbox_padding,
                    bbox[2] + bbox_padding,
                    bbox[3] + bbox_padding,
                    fill='black',
                    outline=''
                )
                
                self.help_text_item = self.canvas.create_text(
                    help_x, help_y,
                    text=help_content,
                    fill='white',
                    font=('Consolas', 12, 'bold'),
                    justify='left'
                )
        
        return "break"
    
    def create_magnifier(self):
        if self.magnifier_window and self.magnifier_window.winfo_exists():
            return
        
        try:
            self.magnifier_window = tk.Toplevel(self.root)
            self.magnifier_window.overrideredirect(True)
            self.magnifier_window.attributes('-topmost', True)
            self.magnifier_window.attributes('-alpha', 0.95)
            
            border_frame = tk.Frame(self.magnifier_window, bg='white', bd=3, relief=tk.SOLID)
            border_frame.pack()
            
            self.magnifier_canvas = tk.Canvas(
                border_frame,
                width=self.magnifier_size,
                height=self.magnifier_size,
                bg='gray',
                highlightthickness=0
            )
            self.magnifier_canvas.pack()
            self.magnifier_window.withdraw()
        except Exception as e:
            pass
    
    def update_magnifier(self, screen_x, screen_y):
        if not self.magnifier_window or not self.magnifier_canvas:
            self.create_magnifier()
        
        if not self.magnifier_window or not self.magnifier_window.winfo_exists():
            return
        
        if not self.bg_screenshot:
            return
        
        try:
            capture_pixels = self.magnifier_size // self.magnifier_zoom
            half_capture = capture_pixels // 2
            
            capture_x1 = int(screen_x - half_capture)
            capture_y1 = int(screen_y - half_capture)
            capture_x2 = int(screen_x + half_capture)
            capture_y2 = int(screen_y + half_capture)
            
            img_width, img_height = self.bg_screenshot.size
            
            if capture_x1 < 0:
                capture_x1 = 0
                capture_x2 = capture_pixels
            if capture_y1 < 0:
                capture_y1 = 0
                capture_y2 = capture_pixels
            if capture_x2 > img_width:
                capture_x2 = img_width
                capture_x1 = img_width - capture_pixels
            if capture_y2 > img_height:
                capture_y2 = img_height
                capture_y1 = img_height - capture_pixels
            
            cropped = self.bg_screenshot.crop((capture_x1, capture_y1, capture_x2, capture_y2))
            zoomed = cropped.resize((self.magnifier_size, self.magnifier_size), Image.NEAREST)
            photo = ImageTk.PhotoImage(zoomed)
            
            self.magnifier_canvas.delete('all')
            self.magnifier_canvas.create_image(0, 0, anchor='nw', image=photo)
            self.magnifier_canvas.image = photo
            
            cursor_in_capture_x = screen_x - capture_x1
            cursor_in_capture_y = screen_y - capture_y1
            cursor_in_magnifier_x = cursor_in_capture_x * self.magnifier_zoom
            cursor_in_magnifier_y = cursor_in_capture_y * self.magnifier_zoom
            
            crosshair_size = 12
            self.magnifier_canvas.create_line(
                cursor_in_magnifier_x, cursor_in_magnifier_y - crosshair_size,
                cursor_in_magnifier_x, cursor_in_magnifier_y + crosshair_size,
                fill='red', width=2
            )
            self.magnifier_canvas.create_line(
                cursor_in_magnifier_x - crosshair_size, cursor_in_magnifier_y,
                cursor_in_magnifier_x + crosshair_size, cursor_in_magnifier_y,
                fill='red', width=2
            )
            
            dot_size = 2
            self.magnifier_canvas.create_oval(
                cursor_in_magnifier_x - dot_size, cursor_in_magnifier_y - dot_size,
                cursor_in_magnifier_x + dot_size, cursor_in_magnifier_y + dot_size,
                fill='red', outline='white', width=1
            )
            
            mag_x = int(screen_x) + 30
            mag_y = int(screen_y) + 30
            
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            
            if mag_x + self.magnifier_size + 50 > screen_width:
                mag_x = int(screen_x) - self.magnifier_size - 30
            if mag_y + self.magnifier_size + 50 > screen_height:
                mag_y = int(screen_y) - self.magnifier_size - 30
            
            self.magnifier_window.geometry(f"+{mag_x}+{mag_y}")
            self.magnifier_window.deiconify()
            self.magnifier_window.lift()
            
        except Exception as e:
            pass
    
    def hide_magnifier(self):
        try:
            if self.magnifier_window and self.magnifier_window.winfo_exists():
                self.magnifier_window.withdraw()
        except:
            pass
    
    def on_arrow_key(self, event):
        if not self.region_selected:
            if not self.restore_last_capture():
                return "break"
        
        if self.start_x is None:
            return "break"
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        mode = self.last_adjust_mode
        
        delta_x = 0
        delta_y = 0
        if event.keysym == 'Left':
            delta_x = -1
        elif event.keysym == 'Right':
            delta_x = 1
        elif event.keysym == 'Up':
            delta_y = -1
        elif event.keysym == 'Down':
            delta_y = 1
        
        if mode == 'inside':
            x1 += delta_x
            x2 += delta_x
            y1 += delta_y
            y2 += delta_y
        elif mode == 'tl':
            x1 += delta_x
            y1 += delta_y
        elif mode == 'tr':
            x2 += delta_x
            y1 += delta_y
        elif mode == 'bl':
            x1 += delta_x
            y2 += delta_y
        elif mode == 'br':
            x2 += delta_x
            y2 += delta_y
        elif mode == 'left':
            x1 += delta_x
        elif mode == 'right':
            x2 += delta_x
        elif mode == 'top':
            y1 += delta_y
        elif mode == 'bottom':
            y2 += delta_y
        
        if mode != 'inside':
            if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
                return "break"
        
        self.start_x = x1
        self.start_y = y1
        self.end_x = x2
        self.end_y = y2
        
        self.update_display()
        
        if mode != 'inside':
            if mode == 'tl':
                mag_x, mag_y = x1, y1
            elif mode == 'tr':
                mag_x, mag_y = x2, y1
            elif mode == 'bl':
                mag_x, mag_y = x1, y2
            elif mode == 'br':
                mag_x, mag_y = x2, y2
            elif mode == 'left':
                mag_x, mag_y = x1, (y1 + y2) // 2
            elif mode == 'right':
                mag_x, mag_y = x2, (y1 + y2) // 2
            elif mode == 'top':
                mag_x, mag_y = (x1 + x2) // 2, y1
            elif mode == 'bottom':
                mag_x, mag_y = (x1 + x2) // 2, y2
            else:
                mag_x, mag_y = x2, y2
            
            self.update_magnifier(mag_x, mag_y)
            
            if hasattr(self, 'hide_magnifier_timer'):
                self.root.after_cancel(self.hide_magnifier_timer)
            self.hide_magnifier_timer = self.root.after(500, self.hide_magnifier)
        
        return "break"
    
    def restore_last_capture(self):
        """Restore the position at current history index, or the last one if index is -1"""
        if self.capture_history:
            if self.capture_history_index == -1:
                self.capture_history_index = len(self.capture_history) - 1
            
            x1, y1, x2, y2 = self.capture_history[self.capture_history_index]
            
            self.start_x = x1
            self.start_y = y1
            self.end_x = x2
            self.end_y = y2
            
            self.region_selected = True
            self.is_selecting = False
            
            self.update_display()
            return True
        return False
    
    def restore_last_capture_and_activate(self):
        """Restore last capture and activate keyboard input"""
        restored = self.restore_last_capture()
        if self.canvas:
            self.canvas.focus_set()
            self.canvas.update()
    
    def go_to_previous_capture(self, event=None):
        """Go to PREVIOUS capture (Backspace) - wraps to last if at first"""
        if not self.capture_history:
            return "break"
        
        if self.capture_history_index == -1:
            self.capture_history_index = len(self.capture_history) - 1
        elif self.capture_history_index > 0:
            self.capture_history_index -= 1
        else:
            self.capture_history_index = len(self.capture_history) - 1
        
        x1, y1, x2, y2 = self.capture_history[self.capture_history_index]
        
        self.start_x = x1
        self.start_y = y1
        self.end_x = x2
        self.end_y = y2
        
        self.region_selected = True
        self.is_selecting = False
        
        self.update_display()
        
        return "break"
    
    def go_to_next_capture(self, event=None):
        """Go to NEXT capture (Tab) - wraps to first if at last"""
        if not self.capture_history:
            return "break"
        
        if self.capture_history_index == -1:
            self.capture_history_index = 0
        elif self.capture_history_index < len(self.capture_history) - 1:
            self.capture_history_index += 1
        else:
            self.capture_history_index = 0
        
        x1, y1, x2, y2 = self.capture_history[self.capture_history_index]
        
        self.start_x = x1
        self.start_y = y1
        self.end_x = x2
        self.end_y = y2
        
        self.region_selected = True
        self.is_selecting = False
        
        self.update_display()
        
        return "break"
    
    def save_current_capture_position(self):
        """Save current position to history"""
        if self.start_x is not None and self.end_x is not None:
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            x2 = max(self.start_x, self.end_x)
            y2 = max(self.start_y, self.end_y)
            
            new_capture = (x1, y1, x2, y2)
            
            try:
                existing_index = self.capture_history.index(new_capture)
                self.capture_history_index = existing_index
            except ValueError:
                self.capture_history.append(new_capture)
                self.capture_history_index = len(self.capture_history) - 1
    
    def check_for_activation_signal(self):
        if self.socket_check_callback and not self.is_active:
            self.socket_check_callback()
    
    def activate_capture_mode(self):
        if self.is_active:
            return
        
        self.is_active = True
        self.capture_requested = False
        
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.end_y = None
        self.is_selecting = False
        self.is_resizing = False
        self.is_moving = False
        self.resize_mode = None
        self.region_selected = False
        self.corner_texts = []
        self.size_texts = []
        self.dark_rects = []
        self.last_adjust_mode = 'inside'
        self.help_bg_rect = None
        self.help_text_item = None
        
        self.bg_screenshot = ImageGrab.grab()
        
        self.root = tk.Tk()
        self.root.attributes('-fullscreen', True)
        self.root.attributes('-topmost', True)
        
        self.root.focus_force()
        self.root.lift()
        
        self.root.bind('<Control-c>', self.quit_program)
        
        self.canvas = tk.Canvas(
            self.root,
            cursor='cross',
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.focus_set()
        
        self.bg_photo = ImageTk.PhotoImage(self.bg_screenshot)
        self.bg_item = self.canvas.create_image(0, 0, anchor='nw', image=self.bg_photo)
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        self.initial_dark_overlay = self.canvas.create_rectangle(
            0, 0, screen_width, screen_height,
            fill='gray',
            stipple='gray50',
            outline=''
        )
        
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<Motion>', self.on_mouse_move)
        
        self.root.bind('<Return>', self.save_screenshot)
        self.root.bind('<Escape>', self.copy_to_clipboard)
        self.root.bind('<Left>', self.on_arrow_key)
        self.root.bind('<Right>', self.on_arrow_key)
        self.root.bind('<Up>', self.on_arrow_key)
        self.root.bind('<Down>', self.on_arrow_key)
        self.root.bind('<BackSpace>', self.go_to_previous_capture)
        self.root.bind('<Tab>', self.go_to_next_capture)
        self.root.bind('i', self.toggle_info_display)
        self.root.bind('I', self.toggle_info_display)
        self.root.bind('h', self.toggle_help_display)
        self.root.bind('H', self.toggle_help_display)
        
        self.canvas.bind('<Return>', self.save_screenshot)
        self.canvas.bind('<Escape>', self.copy_to_clipboard)
        self.canvas.bind('<Left>', self.on_arrow_key)
        self.canvas.bind('<Right>', self.on_arrow_key)
        self.canvas.bind('<Up>', self.on_arrow_key)
        self.canvas.bind('<Down>', self.on_arrow_key)
        self.canvas.bind('<BackSpace>', self.go_to_previous_capture)
        self.canvas.bind('<Tab>', self.go_to_next_capture)
        self.canvas.bind('<KeyPress-i>', self.toggle_info_display)
        self.canvas.bind('<KeyPress-I>', self.toggle_info_display)
        self.canvas.bind('<KeyPress-h>', self.toggle_help_display)
        self.canvas.bind('<KeyPress-H>', self.toggle_help_display)
        
        self.canvas.focus_set()
        self.canvas.focus_force()
        self.root.update()
        
        self.root.after(50, lambda: self.canvas.focus_set())
        self.root.after(100, self.create_magnifier)
        self.root.after(150, lambda: self.canvas.focus_force())
        self.root.after(200, self.restore_last_capture_and_activate)
        self.root.after(300, lambda: self.canvas.focus_set())
        
        self.root.mainloop()
    
    def deactivate_capture_mode(self):
        try:
            self.hide_magnifier()
            if self.magnifier_window:
                try:
                    self.magnifier_window.destroy()
                except:
                    pass
                self.magnifier_window = None
                self.magnifier_canvas = None
            
            if self.root:
                try:
                    self.root.quit()
                    self.root.destroy()
                except:
                    pass
                self.root = None
                self.canvas = None
            
            self.bg_screenshot = None
            self.bg_photo = None
        except:
            pass
        
        self.is_active = False
    
    def quit_program(self, event=None):
        self.should_quit = True
        self.deactivate_capture_mode()
        self.single_instance.cleanup()
        sys.exit(0)
    
    def get_resize_mode(self, x, y):
        if not self.region_selected or self.start_x is None:
            return None
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        threshold = self.resize_threshold
        
        if abs(x - x1) <= threshold and abs(y - y1) <= threshold:
            return 'tl'
        elif abs(x - x2) <= threshold and abs(y - y1) <= threshold:
            return 'tr'
        elif abs(x - x1) <= threshold and abs(y - y2) <= threshold:
            return 'bl'
        elif abs(x - x2) <= threshold and abs(y - y2) <= threshold:
            return 'br'
        
        if abs(x - x1) <= threshold and y1 <= y <= y2:
            return 'left'
        elif abs(x - x2) <= threshold and y1 <= y <= y2:
            return 'right'
        elif abs(y - y1) <= threshold and x1 <= x <= x2:
            return 'top'
        elif abs(y - y2) <= threshold and x1 <= x <= x2:
            return 'bottom'
        
        if x1 <= x <= x2 and y1 <= y <= y2:
            return 'inside'
        
        return None
    
    def update_cursor(self, mode):
        if not self.canvas:
            return
        
        cursor_map = {
            'tl': 'top_left_corner',
            'tr': 'top_right_corner',
            'bl': 'bottom_left_corner',
            'br': 'bottom_right_corner',
            'left': 'left_side',
            'right': 'right_side',
            'top': 'top_side',
            'bottom': 'bottom_side',
            'inside': 'fleur',
        }
        
        if mode in cursor_map:
            self.canvas.config(cursor=cursor_map[mode])
        else:
            self.canvas.config(cursor='cross')
    
    def on_mouse_move(self, event):
        if not self.is_selecting and not self.is_resizing and not self.is_moving:
            mode = self.get_resize_mode(event.x, event.y)
            self.update_cursor(mode)
            
            if mode and mode != 'inside':
                x1 = min(self.start_x, self.end_x)
                y1 = min(self.start_y, self.end_y)
                x2 = max(self.start_x, self.end_x)
                y2 = max(self.start_y, self.end_y)
                
                if mode == 'tl':
                    self.update_magnifier(x1, y1)
                elif mode == 'tr':
                    self.update_magnifier(x2, y1)
                elif mode == 'bl':
                    self.update_magnifier(x1, y2)
                elif mode == 'br':
                    self.update_magnifier(x2, y2)
                elif mode == 'left':
                    self.update_magnifier(x1, event.y)
                elif mode == 'right':
                    self.update_magnifier(x2, event.y)
                elif mode == 'top':
                    self.update_magnifier(event.x, y1)
                elif mode == 'bottom':
                    self.update_magnifier(event.x, y2)
            else:
                self.hide_magnifier()
    
    def on_mouse_down(self, event):
        self.canvas.focus_set()
        
        mode = self.get_resize_mode(event.x, event.y)
        
        if mode == 'inside':
            self.is_moving = True
            self.move_start_x = event.x
            self.move_start_y = event.y
            self.move_offset_x = event.x - min(self.start_x, self.end_x)
            self.move_offset_y = event.y - min(self.start_y, self.end_y)
            self.last_adjust_mode = 'inside'
        elif mode and mode != 'inside':
            self.is_resizing = True
            self.resize_mode = mode
            self.last_adjust_mode = mode
            self.resize_start_x = event.x
            self.resize_start_y = event.y
            
            x1 = min(self.start_x, self.end_x)
            y1 = min(self.start_y, self.end_y)
            x2 = max(self.start_x, self.end_x)
            y2 = max(self.start_y, self.end_y)
            
            if mode == 'tl':
                self.update_magnifier(x1, y1)
            elif mode == 'tr':
                self.update_magnifier(x2, y1)
            elif mode == 'bl':
                self.update_magnifier(x1, y2)
            elif mode == 'br':
                self.update_magnifier(x2, y2)
            elif mode == 'left':
                self.update_magnifier(x1, event.y)
            elif mode == 'right':
                self.update_magnifier(x2, event.y)
            elif mode == 'top':
                self.update_magnifier(event.x, y1)
            elif mode == 'bottom':
                self.update_magnifier(event.x, y2)
        else:
            self.start_x = event.x
            self.start_y = event.y
            self.end_x = event.x
            self.end_y = event.y
            self.is_selecting = True
            self.region_selected = False
            
            self.clear_display()
            self.hide_magnifier()
    
    def on_mouse_drag(self, event):
        if self.is_selecting:
            self.end_x = event.x
            self.end_y = event.y
            self.update_display()
            self.update_magnifier(event.x, event.y)
        elif self.is_resizing:
            self.resize_selection(event.x, event.y)
            self.update_magnifier(event.x, event.y)
        elif self.is_moving:
            self.move_selection(event.x, event.y)
    
    def on_mouse_up(self, event):
        self.canvas.focus_set()
        
        if self.is_selecting:
            self.end_x = event.x
            self.end_y = event.y
            self.is_selecting = False
            
            if abs(self.end_x - self.start_x) < 10 or abs(self.end_y - self.start_y) < 10:
                self.clear_display()
                self.start_x = None
                self.start_y = None
                self.region_selected = False
                self.hide_magnifier()
                return
            
            self.region_selected = True
            self.update_display()
            self.hide_magnifier()
        
        elif self.is_resizing:
            self.is_resizing = False
            self.resize_mode = None
            self.hide_magnifier()
        
        elif self.is_moving:
            self.is_moving = False
            self.move_start_x = None
            self.move_start_y = None
    
    def move_selection(self, x, y):
        if not self.is_moving:
            return
        
        width = abs(self.end_x - self.start_x)
        height = abs(self.end_y - self.start_y)
        
        new_x = x - self.move_offset_x
        new_y = y - self.move_offset_y
        
        self.start_x = new_x
        self.start_y = new_y
        self.end_x = new_x + width
        self.end_y = new_y + height
        
        self.update_display()
    
    def resize_selection(self, x, y):
        if not self.resize_mode:
            return
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        if 'left' in self.resize_mode or self.resize_mode == 'tl' or self.resize_mode == 'bl':
            x1 = x
        if 'right' in self.resize_mode or self.resize_mode == 'tr' or self.resize_mode == 'br':
            x2 = x
        if 'top' in self.resize_mode or self.resize_mode == 'tl' or self.resize_mode == 'tr':
            y1 = y
        if 'bottom' in self.resize_mode or self.resize_mode == 'bl' or self.resize_mode == 'br':
            y2 = y
        
        if abs(x2 - x1) < 10 or abs(y2 - y1) < 10:
            return
        
        self.start_x = x1
        self.start_y = y1
        self.end_x = x2
        self.end_y = y2
        
        self.update_display()
    
    def clear_display(self):
        if hasattr(self, 'initial_dark_overlay') and self.initial_dark_overlay:
            try:
                self.canvas.delete(self.initial_dark_overlay)
                self.initial_dark_overlay = None
            except:
                pass
        
        for rect in self.dark_rects:
            self.canvas.delete(rect)
        self.dark_rects.clear()
        
        self.clear_corner_texts()
        self.clear_size_texts()
    
    def update_display(self):
        if not self.canvas:
            return
        
        if hasattr(self, 'initial_dark_overlay') and self.initial_dark_overlay:
            try:
                self.canvas.delete(self.initial_dark_overlay)
                self.initial_dark_overlay = None
            except:
                pass
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        width = x2 - x1
        height = y2 - y1
        
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        self.clear_display()
        
        if y1 > 0:
            rect = self.canvas.create_rectangle(
                0, 0, screen_width, y1,
                fill='gray',
                stipple='gray50',
                outline=''
            )
            self.dark_rects.append(rect)
        
        if y2 < screen_height:
            rect = self.canvas.create_rectangle(
                0, y2, screen_width, screen_height,
                fill='gray',
                stipple='gray50',
                outline=''
            )
            self.dark_rects.append(rect)
        
        if x1 > 0:
            rect = self.canvas.create_rectangle(
                0, y1, x1, y2,
                fill='gray',
                stipple='gray50',
                outline=''
            )
            self.dark_rects.append(rect)
        
        if x2 < screen_width:
            rect = self.canvas.create_rectangle(
                x2, y1, screen_width, y2,
                fill='gray',
                stipple='gray50',
                outline=''
            )
            self.dark_rects.append(rect)
        
        if self.show_info:
            self.clear_corner_texts()
            
            corner_positions = [
                (x1, y1, f"({x1}, {y1})", 'tl'),
                (x2, y1, f"({x2}, {y1})", 'tr'),
                (x1, y2, f"({x1}, {y2})", 'bl'),
                (x2, y2, f"({x2}, {y2})", 'br'),
            ]
            
            for cx, cy, text, pos in corner_positions:
                if pos == 'tl':
                    tx, ty = cx - 5, cy - 5
                    anchor = 'se'
                elif pos == 'tr':
                    tx, ty = cx + 5, cy - 5
                    anchor = 'sw'
                elif pos == 'bl':
                    tx, ty = cx - 5, cy + 5
                    anchor = 'ne'
                elif pos == 'br':
                    tx, ty = cx + 5, cy + 5
                    anchor = 'nw'
                
                corner_text = self.canvas.create_text(
                    tx, ty,
                    text=text,
                    fill='yellow',
                    font=('Arial', 10, 'bold'),
                    anchor=anchor
                )
                self.corner_texts.append(corner_text)
            
            self.clear_size_texts()
            
            width_top = self.canvas.create_text(
                (x1 + x2) // 2, y1 - 10,
                text=f"W: {width}px",
                fill='cyan',
                font=('Arial', 11, 'bold')
            )
            self.size_texts.append(width_top)
            
            width_bottom = self.canvas.create_text(
                (x1 + x2) // 2, y2 + 10,
                text=f"W: {width}px",
                fill='cyan',
                font=('Arial', 11, 'bold')
            )
            self.size_texts.append(width_bottom)
            
            height_left = self.canvas.create_text(
                x1 - 10, (y1 + y2) // 2,
                text=f"H: {height}px",
                fill='cyan',
                font=('Arial', 11, 'bold'),
                angle=90
            )
            self.size_texts.append(height_left)
            
            height_right = self.canvas.create_text(
                x2 + 10, (y1 + y2) // 2,
                text=f"H: {height}px",
                fill='cyan',
                font=('Arial', 11, 'bold'),
                angle=90
            )
            self.size_texts.append(height_right)
        else:
            self.clear_corner_texts()
            self.clear_size_texts()
    
    def clear_corner_texts(self):
        if not self.canvas:
            return
        for text in self.corner_texts:
            self.canvas.delete(text)
        self.corner_texts.clear()
    
    def clear_size_texts(self):
        if not self.canvas:
            return
        for text in self.size_texts:
            self.canvas.delete(text)
        self.size_texts.clear()
    
    def save_screenshot(self, event=None):
        if self.start_x is None or self.end_x is None:
            if not self.restore_last_capture():
                return "break"
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        self.save_current_capture_position()
        
        self.root.withdraw()
        self.root.update()
        
        import time
        time.sleep(0.1)
        
        screenshot = self.bg_screenshot.crop((x1, y1, x2, y2))
        
        try:
            output = io.BytesIO()
            screenshot.convert('RGB').save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
        except Exception as e:
            pass
        
        default_filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        file_path = filedialog.asksaveasfilename(
            title="Save Screenshot",
            defaultextension=".png",
            initialfile=default_filename,
            initialdir=self.last_save_dir,
            filetypes=[
                ("PNG Image", "*.png"),
                ("JPEG Image", "*.jpg"),
                ("All Files", "*.*")
            ]
        )
        
        if file_path:
            self.last_save_dir = os.path.dirname(file_path)
            screenshot.save(file_path)
        
        self.deactivate_capture_mode()
        return "break"
    
    def copy_to_clipboard(self, event=None):
        if self.start_x is None or self.end_x is None:
            if not self.restore_last_capture():
                self.deactivate_capture_mode()
                return "break"
        
        x1 = min(self.start_x, self.end_x)
        y1 = min(self.start_y, self.end_y)
        x2 = max(self.start_x, self.end_x)
        y2 = max(self.start_y, self.end_y)
        
        self.save_current_capture_position()
        
        self.root.withdraw()
        self.root.update()
        
        import time
        time.sleep(0.1)
        
        screenshot = self.bg_screenshot.crop((x1, y1, x2, y2))
        
        try:
            output = io.BytesIO()
            screenshot.convert('RGB').save(output, 'BMP')
            data = output.getvalue()[14:]
            output.close()
            
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()
        except Exception as e:
            pass
        
        self.deactivate_capture_mode()
        return "break"
    
    def run(self):
        if self.single_instance.is_already_running():
            if self.single_instance.signal_existing_instance():
                pass
            return
        
        self.socket_check_callback = self.single_instance.start_listening(
            lambda: setattr(self, 'capture_requested', True)
        )
        
        self.activate_capture_mode()
        
        try:
            while not self.should_quit:
                import time
                time.sleep(0.1)
                
                if self.socket_check_callback:
                    self.socket_check_callback()
                
                if self.capture_requested and not self.is_active:
                    self.activate_capture_mode()
        except KeyboardInterrupt:
            pass
        finally:
            self.single_instance.cleanup()
            self.deactivate_capture_mode()
            sys.exit(0)


def main():
    app = ScreenCaptureApp()
    app.run()


if __name__ == "__main__":
    main()