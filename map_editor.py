import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.style import ThemeDefinition, Colors

from PIL import Image, ImageDraw, ImageTk
import yaml
import math
import os

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

GEORG_THEME = ThemeDefinition(
    name="georg_dark",
    mode="dark",
    colors=Colors(
        primary="#AC362A",
        secondary="#3a1f1c",
        success="#4caf50",
        info="#D9694F",
        warning="#ff9800",
        danger="#e63946",
        light="#f5f5f5",
        dark="#1a1210",
        bg="#1a1210",
        fg="#f0e0dc",
        selectbg="#AC362A",
        selectfg="#ffffff",
        border="#5c2c24",
        inputfg="#f0e0dc",
        inputbg="#2b1a17",
        active="#7a3229",
    )
)


class MapEditor:

    def __init__(self, root):

        self.root = root
        self.root.title("GEORG Map Editor")
        self.style = root.style 
        
        # Data
        

        self.image = None
        self.photo = None  

        self.objects = {}
        self.polygons = []

        self.current_polygon_points = None
        self.zone_start = None
        self.zone_preview_rect = None   

        # hover UI
        self.hover_dot = None
        self.hovered_item = None

        

        
        # Pixel-Art Icons pro Objekttyp (aus icons/<typ>.png geladen)
        

        self._pixel_art_sources = {}   # obj_type -> geladene PIL-Quellgrafik
        self.icon_cache = {}           # (obj_type, size) -> ImageTk.PhotoImage

        
        # ROS2 parameters (map pixel <-> world meters)
        

        self.resolution = 0.05
        self.origin = (0.0, 0.0)

        
        # View parameters (image pixel <-> screen/canvas pixel)
        

        self.zoom = 1.0
        self.min_zoom = 0.05
        self.max_zoom = 20.0

        # Pan offset, in screen pixels, of the image's top-left corner
        self.pan_x = 0
        self.pan_y = 0

        # for click-drag panning
        self._pan_start = None
        self._pan_origin_at_start = None

        
        # UI
        

        top = ttk.Frame(root)
        top.pack(fill="x")

        ttk.Button(top, text="Load Map", command=self.load_map, bootstyle="primary").pack(side="left", padx=5, pady=5)
        ttk.Button(top, text="Load YAML", command=self.load_yaml, bootstyle="secondary").pack(side="left", padx=5, pady=5)
        ttk.Button(top, text="Save YAML", command=self.save_yaml, bootstyle="success").pack(side="left", padx=5, pady=5)
        ttk.Button(top, text="Clear", command=self.clear_all, bootstyle="danger-outline").pack(side="left", padx=5, pady=5)

        self.mode = tk.StringVar(value="object")
        self.mode.trace_add("write", self.on_mode_change)

        ttk.Combobox(
            top,
            textvariable=self.mode,
            values=["object", "rectangle", "polygon"],
            width=18,
            state="readonly",
            bootstyle="info"
        ).pack(side="left")

        self.object_type = tk.StringVar(value="door")

        # Keep a reference so we can show/hide this specific widget
        self.object_type_combo = ttk.Combobox(
            top,
            textvariable=self.object_type,
            values=["door", "seat", "start", "beverages"],
            width=20,
            state="readonly",
            bootstyle="info"
        )
        self.object_type_combo.pack(side="left")

        # Zoom controls
        ttk.Button(top, text="-", width=3, command=lambda: self.zoom_by(1 / 1.2), bootstyle="secondary-outline").pack(side="left", padx=(20, 0))
        ttk.Button(top, text="+", width=3, command=lambda: self.zoom_by(1.2), bootstyle="secondary-outline").pack(side="left")
        ttk.Button(top, text="Fit", command=self.zoom_fit, bootstyle="secondary-outline").pack(side="left", padx=5)
        self.zoom_label = ttk.Label(top, text="100%")
        self.zoom_label.pack(side="left", padx=5)

        # Canvas (links) + Übersichts-Sidebar (rechts), beide in einem
        # gemeinsamen Container, damit die Sidebar am rechten Rand fixiert bleibt
        middle = ttk.Frame(root)
        middle.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(middle, bg=self.style.colors.bg, highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Button-3>", self.on_right_click)

        # Zoom with mouse wheel
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel) # Windows
        self.canvas.bind("<Button-4>", self.on_mouse_wheel) # Linux
        self.canvas.bind("<Button-5>", self.on_mouse_wheel) # Linux

        # Pan with middle-click drag
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start)
        self.canvas.bind("<B2-Motion>", self.on_pan_move)

        self.canvas.bind("<Configure>", self.on_canvas_resize)

        # Cancel drawing
        self.root.bind("<Escape>", lambda e: self.cancel_current_drawing())

        # Sidebar with Objects/Zones with divider to map screen

        divider = tk.Frame(middle, width=4, bg=self.style.colors.info)
        divider.pack(side="left", fill="y")

        sidebar = ttk.Frame(middle, width=260)
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)

        ttk.Label(sidebar, text="Objekte / Zonen:", font=("", 11, "bold")).pack(
            anchor="w", padx=8, pady=(8, 4)
        )

        sidebar_body = ttk.Frame(sidebar)
        sidebar_body.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))

        sidebar_body.bind("<Enter>", lambda e: self._activate_sidebar_scroll())
        sidebar_body.bind("<Leave>", lambda e: self._deactivate_sidebar_scroll())

        self.sidebar_canvas = tk.Canvas(sidebar_body, highlightthickness=0)
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)

        sidebar_scroll = ttk.Scrollbar(sidebar_body, orient="vertical", command=self.sidebar_canvas.yview)
        sidebar_scroll.pack(side="right", fill="y")
        self.sidebar_canvas.configure(yscrollcommand=sidebar_scroll.set)

        self.sidebar_list_frame = ttk.Frame(self.sidebar_canvas)
        self.sidebar_canvas.create_window((0, 0), window=self.sidebar_list_frame, anchor="nw")

        self.sidebar_list_frame.bind(
            "<Configure>",
            lambda e: self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
        )

        self.refresh_sidebar()

    
    # hide object drop down menu

    def on_mode_change(self, *args):

        if self.mode.get() == "object":
            if not self.object_type_combo.winfo_ismapped():
                self.object_type_combo.pack(side="left")
        else:
            if self.object_type_combo.winfo_ismapped():
                self.object_type_combo.pack_forget()

        
        self.cancel_current_drawing()


    def cancel_current_drawing(self):

        if self.zone_preview_rect:
            self.canvas.delete(self.zone_preview_rect)
            self.zone_preview_rect = None

        self.zone_start = None
        self.current_polygon_points = None

        if self.hover_dot:
            self.canvas.delete(self.hover_dot)
            self.hover_dot = None

        self.redraw()

    
    # Load Map
    

    def load_map(self):

        filename = filedialog.askopenfilename(
            filetypes=[("Images", "*.png *.jpg *.jpeg *.pgm"), ("All Files", "*.*")]
        )

        if not filename:
            return

        self.image = Image.open(filename)

        yaml_path = os.path.splitext(filename)[0] + ".yaml"
        if os.path.isfile(yaml_path):
            with open(yaml_path, "r") as f:
                map_data = yaml.safe_load(f) or {}

            self.resolution = float(map_data.get("resolution", self.resolution))
            origin = map_data.get("origin", [0.0, 0.0, 0.0])
            self.origin = (float(origin[0]), float(origin[1]))
        else:
            self.origin = (0.0, 0.0)  # <-- Fallback statt leerem Tupel
            messagebox.showwarning(
                "No map.yaml found",
                f"No matching YAML found at:\n{yaml_path}\n\n"
                "Using default resolution/origin — annotated coordinates will "
                "NOT match the real ROS map frame unless you set them manually."
            )

        self.root.update_idletasks()
        self.zoom_fit()

    
    # COORD CONVERSION
    # Two layers, composed:
    #   world (meters)  <->  image pixel (map pixel, what's stored in YAML)
    #   image pixel     <->  screen/canvas pixel (affected by zoom + pan)
    

    # --- world <-> image pixel ---

    def image_px_to_world(self, px, py):
        return [
            round(px * self.resolution + self.origin[0], 3),
            round((self.image.height - py) * self.resolution + self.origin[1], 3)
        ]

    def world_to_image_px(self, x, y):
        return (
            (x - self.origin[0]) / self.resolution,
            self.image.height - (y - self.origin[1]) / self.resolution
        )

    # --- image pixel <-> screen pixel (zoom/pan layer) ---

    def image_px_to_screen(self, px, py):
        return (
            px * self.zoom + self.pan_x,
            py * self.zoom + self.pan_y
        )

    def screen_to_image_px(self, sx, sy):
        return (
            (sx - self.pan_x) / self.zoom,
            (sy - self.pan_y) / self.zoom
        )

    # --- convenience: world <-> screen, composing both layers ---

    def world_to_screen(self, x, y):
        px, py = self.world_to_image_px(x, y)
        return self.image_px_to_screen(px, py)

    def screen_to_world(self, sx, sy):
        px, py = self.screen_to_image_px(sx, sy)
        return self.image_px_to_world(px, py)

    def pixel_to_world(self, sx, sy):
        return self.screen_to_world(sx, sy)

    def world_to_pixel(self, x, y):
        sx, sy = self.world_to_screen(x, y)
        return (int(sx), int(sy))

    
    # Zoom function
    

    def zoom_by(self, factor, center=None):
        """Zoom in/out, keeping the given screen point (or canvas center) fixed."""
        if self.image is None:
            return

        if center is None:
            center = (self.canvas.winfo_width() / 2, self.canvas.winfo_height() / 2)

        old_zoom = self.zoom
        new_zoom = max(self.min_zoom, min(self.max_zoom, old_zoom * factor))
        if new_zoom == old_zoom:
            return

        cx, cy = center

        img_x, img_y = self.screen_to_image_px(cx, cy)

        self.zoom = new_zoom

        self.pan_x = cx - img_x * self.zoom
        self.pan_y = cy - img_y * self.zoom

        self.render_scaled_image()
        self.redraw()
        self.update_zoom_label()

    # fit the map onto the window

    def zoom_fit(self):
    
        if self.image is None:
            return

        cw = max(self.canvas.winfo_width(), 1)
        ch = max(self.canvas.winfo_height(), 1)

        iw, ih = self.image.width, self.image.height

        scale = min(cw / iw, ch / ih)
        scale = max(self.min_zoom, min(self.max_zoom, scale))

        self.zoom = scale

        # Center image in canvas
        self.pan_x = (cw - iw * self.zoom) / 2
        self.pan_y = (ch - ih * self.zoom) / 2

        self.render_scaled_image()
        self.redraw()
        self.update_zoom_label()

    def update_zoom_label(self):
        self.zoom_label.config(text=f"{self.zoom * 100:.0f}%")

    def render_scaled_image(self):
        
        if self.image is None:
            return

        w = max(1, int(self.image.width * self.zoom))
        h = max(1, int(self.image.height * self.zoom))

        resample = Image.NEAREST if self.zoom >= 1.0 else Image.BILINEAR
        scaled = self.image.resize((w, h), resample)
        self.photo = ImageTk.PhotoImage(scaled)

    def on_mouse_wheel(self, event):
        if self.image is None:
            return

        # Normalize delta across platforms
        if event.num == 4:
            factor = 1.1
        elif event.num == 5:
            factor = 1 / 1.1
        else:
            factor = 1.1 if event.delta > 0 else 1 / 1.1

        self.zoom_by(factor, center=(event.x, event.y))


    def _activate_sidebar_scroll(self):
        self.sidebar_canvas.bind_all("<MouseWheel>", self.on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-4>", self.on_sidebar_mousewheel)
        self.sidebar_canvas.bind_all("<Button-5>", self.on_sidebar_mousewheel)

    def _deactivate_sidebar_scroll(self):
        self.sidebar_canvas.unbind_all("<MouseWheel>")
        self.sidebar_canvas.unbind_all("<Button-4>")
        self.sidebar_canvas.unbind_all("<Button-5>")

    def on_sidebar_mousewheel(self, event):

        content_height = self.sidebar_list_frame.winfo_height()
        visible_height = self.sidebar_canvas.winfo_height()

        if content_height <= visible_height:
            return  # Liste passt komplett rein — nichts zu scrollen

        if event.num == 4:
            self.sidebar_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.sidebar_canvas.yview_scroll(1, "units")
        else:
            self.sidebar_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def on_pan_start(self, event):
        self._pan_start = (event.x, event.y)
        self._pan_origin_at_start = (self.pan_x, self.pan_y)

    def on_pan_move(self, event):
        if self._pan_start is None:
            return

        dx = event.x - self._pan_start[0]
        dy = event.y - self._pan_start[1]

        self.pan_x = self._pan_origin_at_start[0] + dx
        self.pan_y = self._pan_origin_at_start[1] + dy

        self.redraw()

    def on_canvas_resize(self, event):

        if self.image is not None:
            self.redraw()

    
    # Save yaml file
    

    def save_yaml(self):

        filename = filedialog.asksaveasfilename(
            defaultextension=".yaml",
            filetypes=[("YAML", "*.yaml")]
        )

        if not filename:
            return

        map_section = {
            "resolution": self.resolution,
            "origin": list(self.origin)
        }

        if self.image is not None:
            map_section["width_px"] = self.image.width
            map_section["height_px"] = self.image.height
            map_section["width_m"] = round(self.image.width * self.resolution, 4)
            map_section["height_m"] = round(self.image.height * self.resolution, 4)
        else:
            messagebox.showwarning(
                "No map image loaded",
                "Saving without a loaded map image — width_m/height_m will "
                "not be written, so downstream tools (e.g. the A* planner) "
                "will have to guess the room extent from annotated features."
            )

        data = {
            "map": map_section,
            "objects": self.objects,
            "polygons": self.polygons
        }

        with open(filename, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)

        messagebox.showinfo("Saved", f"Saved:\n{filename}")

    
    # Load yaml file
    

    def load_yaml(self):

        filename = filedialog.askopenfilename(filetypes=[("YAML", "*.yaml")])
        if not filename:
            return

        with open(filename, "r") as f:
            data = yaml.safe_load(f) or {}

        map_section = data.get("map", {})
        if "resolution" in map_section:
            self.resolution = float(map_section["resolution"])
        if "origin" in map_section:
            origin = map_section["origin"]
            self.origin = (float(origin[0]), float(origin[1]))

        self.objects = data.get("objects", {})
        self.polygons = data.get("polygons", [])

        self.current_polygon_points = None
        self.zone_start = None

        self.refresh_sidebar()
        self.redraw()


    def name_exists(self, name, exclude_kind=None, exclude_key=None):

        for obj_name in self.objects:
            if exclude_kind == "object" and exclude_key == obj_name:
                continue
            if obj_name == name:
                return True


        for idx, p in enumerate(self.polygons):
            if exclude_kind == "polygon" and exclude_key == idx:
                continue
            if p.get("name") == name:
                return True

        return False

    
    # Name requirement check
    

    def ask_required_name(self, title, prompt, initialvalue=None,
                        exclude_kind=None, exclude_key=None):

        value = initialvalue

        while True:
            name = simpledialog.askstring(title, prompt, initialvalue=value)

            if name is None:
                return None

            name = name.strip()

            if not name:
                messagebox.showwarning(
                    "Name required",
                    "A name is required. Please enter a name, or press Cancel "
                    "to discard."
                )
                value = None
                continue

            if self.name_exists(name, exclude_kind=exclude_kind, exclude_key=exclude_key):
                messagebox.showwarning(
                    "Name already exists",
                    f"The name '{name}' is already in use. Please choose "
                    "a different name."
                )
                value = name
                continue

            return name

    
    # Polygon type and color pick options
    
    # avaible colors to choose from
    POLYGON_COLORS = ["red", "blue", "green", "orange", "purple", "black"]
    POLY_TYPE_LABELS = {"obstacle": "Solid obstacle", "wall": "Wall outline", "boundary": "Room boundary",}

    def ask_polygon_type_and_color(self):

        dialog = ttk.Toplevel(self.root)
        dialog.title("Polygon Type & Color")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        result = {"type": None, "color": None}
        type_var = tk.StringVar(value="obstacle")
        color_var = tk.StringVar(value=self.POLYGON_COLORS[0])

        # --- Type: radio buttons ---
        ttk.Label(dialog, text="Polygon type:", font=("", 10, "bold")).pack(
            padx=12, pady=(12, 2), anchor="w"
        )

        type_descriptions = {
            "obstacle": "Solid obstacle (blocks planner)",
            "wall": "Wall outline only",
            "boundary": "Room boundary (outside = blocked)",
        }

        type_frame = ttk.Frame(dialog)
        type_frame.pack(padx=12, pady=(0, 10), anchor="w")

        for value in ["obstacle", "wall", "boundary"]:
            ttk.Radiobutton(
                type_frame,
                text=type_descriptions[value],
                variable=type_var,
                value=value,
            ).pack(fill="x", anchor="w")

        # --- Color: swatch buttons ---
        ttk.Label(dialog, text="Color:", font=("", 10, "bold")).pack(
            padx=12, pady=(0, 2), anchor="w"
        )

        swatch_frame = ttk.Frame(dialog)
        swatch_frame.pack(padx=12, pady=(0, 10))

        swatch_buttons = {}

        def select_color(c):
            color_var.set(c)
            for col, btn in swatch_buttons.items():
                btn.config(relief="sunken" if col == c else "raised",
                           borderwidth=3 if col == c else 1)

        for c in self.POLYGON_COLORS:
            btn = tk.Button(
                swatch_frame,
                bg=c,
                activebackground=c,
                width=3,
                height=1,
                relief="raised",
                command=lambda c=c: select_color(c),
            )
            btn.pack(side="left", padx=3)
            swatch_buttons[c] = btn

        select_color(self.POLYGON_COLORS[0])

        # --- OK / Cancel ---
        def on_ok():
            result["type"] = type_var.get()
            result["color"] = color_var.get()
            dialog.destroy()

        def on_cancel():
            result["type"] = None
            result["color"] = None
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(5, 12))
        ttk.Button(btn_frame, text="OK", width=8, command=on_ok, bootstyle="primary").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Cancel", width=8, command=on_cancel, bootstyle="secondary").pack(side="left", padx=5)

        dialog.bind("<Return>", lambda e: on_ok())
        dialog.bind("<Escape>", lambda e: on_cancel())

        # Center the dialog over the main window
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.wait_window()
        return result["type"], result["color"]

    
    # Click handler
    

    def on_click(self, event):

        if self.image is None:
            return

        mode = self.mode.get()

        
        # Object
        

        if mode == "object":

            name = self.ask_required_name("Object Name", "Enter name:")
            if not name:
                return

            self.objects[name] = {
                "type": self.object_type.get(),
                "frame": "map",
                "position": self.pixel_to_world(event.x, event.y)
            }

            self.refresh_sidebar()

        
        # Rectangle
        

        elif mode == "rectangle":

            if self.zone_start is None:
                self.zone_start = (event.x, event.y)
                return

            if self.zone_preview_rect:
                self.canvas.delete(self.zone_preview_rect)
                self.zone_preview_rect = None

            x1, y1 = self.zone_start
            x2, y2 = event.x, event.y

            name = self.ask_required_name("Zone Name", "Enter zone name:")
            if not name:
                self.zone_start = None
                return

            ptype, color = self.ask_polygon_type_and_color()
            if ptype is None:
                self.zone_start = None
                return

            if ptype == "boundary":
                existing_boundaries = [
                    poly for poly in self.polygons
                    if poly.get("type") == "boundary"
                ]
                if existing_boundaries:
                    proceed = messagebox.askyesno(
                        "Replace boundary?",
                        "A 'boundary' polygon already exists "
                        f"('{existing_boundaries[0]['name']}'). Only "
                        "one boundary polygon is used by the "
                        "navigator. Add this one anyway?"
                    )
                    if not proceed:
                        self.zone_start = None
                        self.redraw()
                        return

            p1 = self.pixel_to_world(x1, y1)
            p2 = self.pixel_to_world(x2, y2)

            self.polygons.append({
                "name": name,
                "type": ptype,
                "frame": "map",
                "color": color,
                "points": [
                    [p1[0], p1[1]],
                    [p2[0], p1[1]],
                    [p2[0], p2[1]],
                    [p1[0], p2[1]],
                ]
            })

            self.zone_start = None
            self.refresh_sidebar()
            self.redraw()

        
        # Polygon
        

        elif mode == "polygon":

            if self.current_polygon_points is None:
                self.current_polygon_points = []

            p = (event.x, event.y)

            # close polygon if near start
            if len(self.current_polygon_points) >= 3:
                fx, fy = self.current_polygon_points[0]
                if math.hypot(event.x - fx, event.y - fy) < 10:

                    name = self.ask_required_name("Polygon Name", "Enter name:")
                    if not name:
                        self.current_polygon_points = None
                        return

                    ptype, color = self.ask_polygon_type_and_color()
                    if ptype is None:
                        self.current_polygon_points = None
                        return

                    if ptype == "boundary":
                        existing_boundaries = [
                            poly for poly in self.polygons
                            if poly.get("type") == "boundary"
                        ]
                        if existing_boundaries:
                            proceed = messagebox.askyesno(
                                "Replace boundary?",
                                "A 'boundary' polygon already exists "
                                f"('{existing_boundaries[0]['name']}'). Only "
                                "one boundary polygon is used by the "
                                "navigator. Add this one anyway?"
                            )
                            if not proceed:
                                self.current_polygon_points = None
                                self.redraw()
                                return

                    self.polygons.append({
                        "name": name,
                        "type": ptype,
                        "frame": "map",
                        "color": color,
                        "points": [
                            self.pixel_to_world(x, y)
                            for x, y in self.current_polygon_points
                        ]
                    })

                    self.current_polygon_points = None
                    self.refresh_sidebar() 
                    self.redraw()
                    return

            self.current_polygon_points.append(p)

        self.redraw()

    
    # Hover function
    

    def on_mouse_move(self, event):

        # --- polygon-closing start-point indicator ---

        if self.current_polygon_points:
            fx, fy = self.current_polygon_points[0]

            if self.hover_dot:
                self.canvas.delete(self.hover_dot)
                self.hover_dot = None

            if math.hypot(event.x - fx, event.y - fy) < 15:
                r = 6
                self.hover_dot = self.canvas.create_oval(
                    fx - r, fy - r,
                    fx + r, fy + r,
                    fill="lime",
                    outline="black",
                    width=2
                )
        elif self.hover_dot:
            self.canvas.delete(self.hover_dot)
            self.hover_dot = None

        # --- highlights on item hovering ---

        if self.image is None:
            return

        new_hovered = self.find_hovered_item(event.x, event.y)

        if new_hovered != self.hovered_item:
            self.hovered_item = new_hovered
            self.redraw()

        # --- shows rectangle being drawn ---

        if self.mode.get() == "rectangle" and self.zone_start is not None:

            if self.zone_preview_rect:
                self.canvas.delete(self.zone_preview_rect)

            x1, y1 = self.zone_start

            self.zone_preview_rect = self.canvas.create_rectangle(
                x1, y1, event.x, event.y,
                outline="yellow", width=2, dash=(4, 2)
            )

    
    # Pixel-Art Icons
    

    @staticmethod
    def _placeholder_icon():
        """Fallback-Icon, falls für einen Objekttyp keine PNG-Datei existiert."""

        size = 12
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rectangle([1, 1, size - 2, size - 2], outline=(200, 60, 60, 255), width=1)
        return img

    def _load_pixel_art_source(self, obj_type):
        """Lädt icons/<obj_type>.png. Fällt auf ein Platzhalter-Icon zurück,
        wenn die Datei fehlt oder nicht gelesen werden kann."""

        path = os.path.join(ICONS_DIR, f"{obj_type}.png")

        try:
            return Image.open(path).convert("RGBA")
        except (FileNotFoundError, OSError):
            return self._placeholder_icon()

    def get_object_icon(self, obj_type, screen_size):
        """Liefert (gecached) ein ImageTk.PhotoImage der passenden Groesse."""

        screen_size = max(8, int(round(screen_size / 2.0)) * 2)  # Cache-Buckets in 2px-Schritten
        key = (obj_type, screen_size)

        if key not in self.icon_cache:
            if obj_type not in self._pixel_art_sources:
                self._pixel_art_sources[obj_type] = self._load_pixel_art_source(obj_type)

            src = self._pixel_art_sources[obj_type]
            scaled = src.resize((screen_size, screen_size), Image.NEAREST)
            self.icon_cache[key] = ImageTk.PhotoImage(scaled)

        return self.icon_cache[key]

    
    # Sidebar: Übersicht aller Objekte/Zonen
    

    def refresh_sidebar(self):

        for child in self.sidebar_list_frame.winfo_children():
            child.destroy()

        icon_size = 28
        colors = self.style.colors

        def add_section_header(text):
            ttk.Label(
                self.sidebar_list_frame, text=text, font=("", 9, "bold")
            ).pack(anchor="w", padx=4, pady=(10, 4))

        def add_row(kind, key, title, coord_text, icon_type):

            card = tk.Frame(
                self.sidebar_list_frame,
                bg=colors.inputbg,
                highlightbackground=colors.border,
                highlightthickness=1,
                bd=0
            )
            card.pack(fill="x", padx=4, pady=3)

            row = tk.Frame(card, bg=colors.inputbg)
            row.pack(fill="x", padx=6, pady=6)

            text_frame = tk.Frame(row, bg=colors.inputbg)
            text_frame.pack(side="left", fill="x", expand=True)

            tk.Label(
                text_frame, text=title, font=("", 9, "bold"),
                bg=colors.inputbg, fg=colors.fg, anchor="w"
            ).pack(anchor="w")
            tk.Label(
                text_frame, text=coord_text, font=("", 8),
                bg=colors.inputbg, fg=colors.get("secondary"), anchor="w"
            ).pack(anchor="w")

            icon = self.get_object_icon(icon_type, icon_size)
            icon_label = tk.Label(row, image=icon, bd=0, bg=colors.inputbg)
            icon_label.image = icon
            icon_label.pack(side="right", padx=(4, 2))

            def on_row_click(event, kind=kind, key=key):
                self.hovered_item = (kind, key)
                self.redraw()

            def on_enter(event, kind=kind, key=key):
                card.config(highlightbackground=colors.info)
                self.hovered_item = (kind, key)
                self.redraw()

            def on_leave(event):
                card.config(highlightbackground=colors.border)
                self.hovered_item = None
                self.redraw()

            for widget in (card, row, text_frame, icon_label):
                widget.bind("<Button-1>", on_row_click)
                widget.bind("<Enter>", on_enter)
                widget.bind("<Leave>", on_leave)

        has_content = bool(self.objects) or bool(self.polygons)

        if self.objects:
            add_section_header("Objekte")
            for name, obj in self.objects.items():
                pos = obj.get("position", [0.0, 0.0])
                coord_text = f"({pos[0]:.2f}, {pos[1]:.2f}) m"
                add_row("object", name, name, coord_text, obj.get("type", "door"))


        if self.polygons:
            if self.objects:
                ttk.Separator(self.sidebar_list_frame, orient="horizontal").pack(
                    fill="x", padx=4, pady=(8, 0)
                )
            add_section_header("Polygone")
            for idx, p in enumerate(self.polygons):
                ptype = p.get("type", "obstacle")
                type_label = self.POLY_TYPE_LABELS.get(ptype, ptype)
                add_row("polygon", idx, p.get("name", "?"), type_label, ptype)        

        if not has_content:
            ttk.Label(
                self.sidebar_list_frame,
                text="Noch keine Objekte oder Zonen eingetragen.",
                font=("", 8),
                wraplength=220,
                justify="left"
            ).pack(anchor="w", padx=4, pady=8)

    
    # Redraw
    

    def redraw(self):

        self.canvas.delete("all")

        if self.hover_dot:
            self.canvas.delete(self.hover_dot)
            self.hover_dot = None

        if self.photo:
            self.canvas.create_image(self.pan_x, self.pan_y, anchor="nw", image=self.photo)

        hovered_kind, hovered_key = (None, None)
        if self.hovered_item is not None:
            hovered_kind, hovered_key = self.hovered_item

        hover_color = self.style.colors.success  # thematischer Akzent statt "cyan"

        # Objects — als Pixel-Art-Icon zur Uebersicht
        for name, obj in self.objects.items():
            x, y = self.world_to_pixel(*obj["position"])

            is_hovered = (hovered_kind == "object" and hovered_key == name)
            tag = f"obj:{name}"

            icon_size = max(14, int(28 * min(self.zoom, 3)))
            icon = self.get_object_icon(obj.get("type", "door"), icon_size)
            half = icon_size // 2

            if is_hovered:
                self.canvas.create_oval(
                    x - half - 3, y - half - 3, x + half + 3, y + half + 3,
                    outline=hover_color, width=2, tags=(tag,)
                )

            self.canvas.create_image(x, y, image=icon, tags=(tag,))

            self.canvas.create_text(
                x + half + 5, y, text=name,
                fill=hover_color if is_hovered else "red",
                font=("", 9, "bold") if is_hovered else ("", 9, "normal"),
                anchor="w",
                tags=(tag,)
            )

        # Polygons for walls, structures and obstacles
        for idx, p in enumerate(self.polygons):

            pts = [self.world_to_pixel(x, y) for x, y in p["points"]]
            color = p.get("color", "red")
            ptype = p.get("type", "obstacle")

            is_boundary = (ptype == "boundary")
            is_hovered = (hovered_kind == "polygon" and hovered_key == idx)

            line_width = 6 if is_boundary else 4
            if is_hovered:
                line_width += 2
            dash = (8, 4) if is_boundary else None
            line_color = hover_color if is_hovered else color

            tag = f"poly:{idx}"

            for i in range(len(pts)):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % len(pts)]

                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=line_color,
                    width=line_width,
                    dash=dash,
                    tags=(tag,)
                )

            label_x, label_y = pts[0]

            label = p["name"] + (" [boundary]" if is_boundary else "")
            self.canvas.create_text(
                label_x + 8, label_y - 8,
                text=label,
                fill=line_color,
                font=("", 9, "bold") if is_hovered else ("", 9, "normal"),
                anchor="w",
                tags=(tag,)
            )

        if self.current_polygon_points:
            pts = self.current_polygon_points
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                self.canvas.create_line(x1, y1, x2, y2, fill="yellow", width=2)
            for x, y in pts:
                self.canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill="yellow")
    
    # Delete function
    

    # Delete hitbox 
    HIT_TOLERANCE_PX = 10

    def on_right_click(self, event):

        if self.image is None:
            return

        sx, sy = event.x, event.y

        obj_name = self.find_object_at(sx, sy)
        poly_idx = self.find_polygon_at(sx, sy)

        menu = tk.Menu(self.canvas, tearoff=0)
        hit_something = False

        if obj_name is not None:
            hit_something = True
            menu.add_command(
                label=f"Delete object '{obj_name}'",
                command=lambda: self.delete_object(obj_name)
            )
            menu.add_command(
                label=f"Rename object '{obj_name}'",
                command=lambda: self.rename_object(obj_name)
            )
            menu.add_separator()


        if poly_idx is not None:
            hit_something = True
            poly_name = self.polygons[poly_idx].get("name", "?")
            menu.add_command(
                label=f"Rename polygon '{poly_name}'",
                command=lambda: self.rename_polygon(poly_idx)
            )
            menu.add_command(
                label=f"Delete polygon '{poly_name}'",
                command=lambda: self.delete_polygon(poly_idx)
            )
            menu.add_separator()

        if not hit_something:
            
            return

        # Remove trailing separator for a cleaner look
        last_index = menu.index("end")
        if last_index is not None:
            menu.delete(last_index)

        menu.tk_popup(event.x_root, event.y_root)

    def find_hovered_item(self, sx, sy):

        # --- 1. Exact tag-based hit ---
        overlapping = self.canvas.find_overlapping(sx, sy, sx, sy)

        for item_id in reversed(overlapping):  # topmost first

            for tag in self.canvas.gettags(item_id):

                if tag.startswith("obj:"):
                    return ("object", tag[len("obj:"):])
                if tag.startswith("poly:"):
                    return ("polygon", int(tag[len("poly:"):]))

        # --- 2. Tolerant geometric fallback (for thin lines/markers) ---
        obj_name = self.find_object_at(sx, sy)
        if obj_name is not None:
            return ("object", obj_name)

        poly_idx = self.find_polygon_at(sx, sy)
        if poly_idx is not None:
            return ("polygon", poly_idx)

        return None

    
    # Hit testing
    

    def find_object_at(self, sx, sy):

        best_name = None
        best_dist = None

        icon_size = max(14, int(28 * min(self.zoom, 3)))
        tolerance = max(self.HIT_TOLERANCE_PX, icon_size // 2)

        for name, obj in self.objects.items():
            ox, oy = self.world_to_pixel(*obj["position"])
            dist = math.hypot(sx - ox, sy - oy)

            if dist <= tolerance and (best_dist is None or dist < best_dist):
                best_name = name
                best_dist = dist

        return best_name

    

    def find_polygon_at(self, sx, sy):

        best_idx = None
        best_dist = None

        for idx, p in enumerate(self.polygons):
            pts = [self.world_to_pixel(x, y) for x, y in p["points"]]
            n = len(pts)

            for i in range(n):
                x1, y1 = pts[i]
                x2, y2 = pts[(i + 1) % n]

                dist = self._point_to_segment_distance(sx, sy, x1, y1, x2, y2)

                if dist <= self.HIT_TOLERANCE_PX and (best_dist is None or dist < best_dist):
                    best_idx = idx
                    best_dist = dist

        return best_idx

    @staticmethod
    def _point_to_segment_distance(px, py, x1, y1, x2, y2):

        dx = x2 - x1
        dy = y2 - y1

        seg_len_sq = dx * dx + dy * dy

        if seg_len_sq == 0:
            # Degenerate segment (a point)
            return math.hypot(px - x1, py - y1)

        # Project point onto the line, clamped to the segment [0, 1]
        t = ((px - x1) * dx + (py - y1) * dy) / seg_len_sq
        t = max(0.0, min(1.0, t))

        closest_x = x1 + t * dx
        closest_y = y1 + t * dy

        return math.hypot(px - closest_x, py - closest_y)

    
    # Delete and rename actions
    

    def delete_object(self, name):
        if name in self.objects:
            del self.objects[name]
            self.refresh_sidebar()
            self.redraw()



    def rename_object(self, old_name):
        if old_name not in self.objects:
            return

        new_name = self.ask_required_name(
            "Rename Object", "Enter new name:",
            initialvalue=old_name,
            exclude_kind="object", exclude_key=old_name
        )

        if not new_name or new_name == old_name:
            return

        self.objects[new_name] = self.objects.pop(old_name)
        self.refresh_sidebar()
        self.redraw()



    def rename_polygon(self, idx):
        if not (0 <= idx < len(self.polygons)):
            return

        old_name = self.polygons[idx].get("name", "")

        new_name = self.ask_required_name(
            "Rename Polygon", "Enter new name:",
            initialvalue=old_name,
            exclude_kind="polygon", exclude_key=idx
        )

        if not new_name or new_name == old_name:
            return

        self.polygons[idx]["name"] = new_name
        self.refresh_sidebar() 
        self.redraw()    


    def delete_polygon(self, idx):
        if 0 <= idx < len(self.polygons):
            del self.polygons[idx]
            self.refresh_sidebar() 
            self.redraw()

    
    # Clear all objects/structures/polygons
    

    def clear_all(self):

        self.objects = {}
        self.polygons = []
        self.current_polygon_points = None

        self.refresh_sidebar()
        self.redraw()



# Main function


def main():

    root = ttk.Window(themename="darkly")
    root.style.register_theme(GEORG_THEME)
    root.style.theme_use("georg_dark")

    root.geometry("1200x800")
    MapEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
