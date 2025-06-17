import ctypes
import pygame
import win32gui
import win32con
from PIL import Image, ImageSequence
import numpy as np
import tkinter as tk
from tkinter import filedialog, ttk, messagebox

STANDARD_GIFS = {
    "Cat": "cat.gif",
    "Fox": "Fox.gif",
    "Fox2": "fox2.gif",
}

def is_similar(color1, color2, tolerance=10):
    return all(abs(c1 - c2) <= tolerance for c1, c2 in zip(color1, color2))

def flood_fill_transparency(image, tolerance=20):
    img = image.convert("RGBA")
    pixels = np.array(img, dtype=np.uint8)
    h, w, _ = pixels.shape
    reference_color = pixels[0, w-1, :3]
    visited = np.zeros((h, w), dtype=bool)
    mask = np.zeros((h, w), dtype=bool)
    stack = [(0, w-1)]
    visited[0, w-1] = True
    
    while stack:
        y, x = stack.pop()
        mask[y, x] = True
        for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not visited[ny, nx]:
                pixel_color = pixels[ny, nx, :3]
                if not is_similar(pixel_color, [0, 0, 0], tolerance=30) and is_similar(pixel_color, reference_color, tolerance):
                    stack.append((ny, nx))
                    visited[ny, nx] = True
    
    for y in range(h):
        for x in range(w):
            if mask[y, x]:
                pixels[y, x] = (0, 0, 0, 0)
    
    return Image.fromarray(pixels)

def process_gif(input_gif, output_gif, tolerance=100):
    img = Image.open(input_gif)
    frames = []
    durations = []
    
    for frame in ImageSequence.Iterator(img):
        processed_frame = flood_fill_transparency(frame, tolerance)
        frames.append(processed_frame.copy())
        durations.append(frame.info.get('duration', 100))
    
    frames[0].save(output_gif, save_all=True, append_images=frames[1:], loop=0, duration=durations, disposal=2, transparency=0)

class GifOverlay:
    def __init__(self, gif_path, width, height, fps):
        self.gif_path = gif_path
        self.width = width
        self.height = height
        self.fps = fps
        self.frames = []

        # Скрываем консоль
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
        pygame.init()

        # Пурпурный как ключ прозрачности
        self.transparency_key_rgb = (255, 0, 255)
        self.transparency_key = (255 << 16) | (0 << 8) | 255

        # Создаем окно
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.NOFRAME)
        hwnd = pygame.display.get_wm_info()['window']
        
        # Настраиваем стиль окна
        styles = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        styles |= win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, styles)
        
        # Устанавливаем цветовой ключ
        win32gui.SetLayeredWindowAttributes(hwnd, self.transparency_key, 0, win32con.LWA_COLORKEY)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

        # Загружаем GIF
        self.load_gif()

        self.frame_count = len(self.frames)
        self.current_frame = 0
        self.clock = pygame.time.Clock()

    def load_gif(self):
        gif = Image.open(self.gif_path)
        original_width, original_height = gif.size

        # Рассчитываем пропорции
        scale_factor = min(self.width / original_width, self.height / original_height)
        new_width = int(original_width * scale_factor)
        new_height = int(original_height * scale_factor)

        # Обновляем окно Pygame
        self.width, self.height = new_width, new_height
        self.screen = pygame.display.set_mode((self.width, self.height), pygame.NOFRAME)

        try:
            while True:
                frame = gif.copy().convert('RGBA')
                # Используем NEAREST для избежания интерполяции
                frame = frame.resize((self.width, self.height), Image.NEAREST)

                # Костыль: фильтрация с защитой черных пикселей
                pixels = np.array(frame, dtype=np.uint8)
                h, w, _ = pixels.shape
                for y in range(h):
                    for x in range(w):
                        pixel = pixels[y, x]
                        # Убираем пиксели, близкие к пурпурному, но сохраняем черные
                        if is_similar(pixel[:3], self.transparency_key_rgb, tolerance=50) and not is_similar(pixel[:3], [0, 0, 0], tolerance=30):
                            pixels[y, x] = (0, 0, 0, 0)

                frame = Image.fromarray(pixels)

                # Создаем поверхность и заполняем ключевым цветом
                pygame_frame = pygame.Surface((self.width, self.height))
                pygame_frame.fill(self.transparency_key_rgb)

                mode = frame.mode
                size = frame.size
                data = frame.tobytes()
                temp_frame = pygame.image.fromstring(data, size, mode)

                pygame_frame.blit(temp_frame, (0, 0))
                pygame_frame.set_colorkey(self.transparency_key_rgb)
                self.frames.append(pygame_frame)

                gif.seek(len(self.frames))
        except EOFError:
            pass

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.MOUSEBUTTONDOWN and event.button == 3):
                    running = False

            hwnd_active = win32gui.GetForegroundWindow()
            if hwnd_active:
                rect = win32gui.GetWindowRect(hwnd_active)
                x, y, _, _ = rect
                gif_x = x
                gif_y = y - self.height
                win32gui.SetWindowPos(pygame.display.get_wm_info()['window'], win32con.HWND_TOPMOST,
                                      gif_x, gif_y, 0, 0, win32con.SWP_NOSIZE)

            self.screen.fill(self.transparency_key_rgb)
            self.screen.blit(self.frames[self.current_frame], (0, 0))
            self.current_frame = (self.current_frame + 1) % self.frame_count
            pygame.display.flip()
            self.clock.tick(self.fps)

        pygame.quit()

# UI и остальные функции остаются без изменений
def select_gif():
    filepath = filedialog.askopenfilename(filetypes=[("GIF файлы", "*.gif")])
    if filepath:
        gif_entry.delete(0, tk.END)
        gif_entry.insert(0, filepath)
        update_gif_size(filepath)

def update_gif_size(filepath):
    try:
        gif = Image.open(filepath)
        width, height = gif.size
        size_entry.delete(0, tk.END)
        size_entry.insert(0, str(width))
    except Exception:
        pass

def select_standard_gif(event):
    gif_name = standard_gif_combobox.get()
    if gif_name in STANDARD_GIFS:
        gif_path = STANDARD_GIFS[gif_name]
        gif_entry.delete(0, tk.END)
        gif_entry.insert(0, gif_path)
        update_gif_size(gif_path)

def start_overlay():
    gif_path = gif_entry.get()
    if not gif_path:
        messagebox.showerror("Ошибка", "Выберите GIF файл")
        return

    fps = int(fps_entry.get())
    size_value = int(size_entry.get())
    width = height = size_value

    app.destroy()
    overlay = GifOverlay(gif_path, width, height, fps)
    overlay.run()

def process_and_run():
    gif_path = gif_entry.get()
    if not gif_path:
        messagebox.showerror("Ошибка", "Выберите GIF файл")
        return

    output_gif = gif_path.rsplit('.', 1)[0] + "_transparent.gif"
    try:
        process_gif(gif_path, output_gif, tolerance=10)
        fps = int(fps_entry.get())
        size_value = int(size_entry.get())
        width = height = size_value

        app.destroy()
        overlay = GifOverlay(output_gif, width, height, fps)
        overlay.run()
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось обработать GIF: {str(e)}")

# UI
app = tk.Tk()
app.title("Настройка GIF Overlay")
app.geometry("300x300")

frame = ttk.Frame(app, padding=10)
frame.pack()

ttk.Label(frame, text="GIF файл:").pack()
gif_entry = ttk.Entry(frame, width=30)
gif_entry.pack()
ttk.Button(frame, text="Выбрать GIF", command=select_gif).pack()

standard_gif_combobox = ttk.Combobox(frame, values=list(STANDARD_GIFS.keys()))
standard_gif_combobox.pack()
standard_gif_combobox.bind("<<ComboboxSelected>>", select_standard_gif)

size_frame = ttk.Frame(app, padding=5)
size_frame.pack()
ttk.Label(size_frame, text="Размер (px):").pack(side=tk.LEFT)
size_entry = ttk.Entry(size_frame, width=8)
size_entry.pack(side=tk.LEFT)

fps_frame = ttk.Frame(app, padding=5)
fps_frame.pack()
ttk.Label(fps_frame, text="FPS:").pack(side=tk.LEFT)
fps_entry = ttk.Entry(fps_frame, width=8)
fps_entry.insert(0, "18")
fps_entry.pack(side=tk.LEFT)

ttk.Button(app, text="Запустить", command=start_overlay).pack(pady=5)
ttk.Button(app, text="Удалить фон и запустить", command=process_and_run).pack(pady=5)

app.mainloop()