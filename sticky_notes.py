#!/usr/bin/env python3
import os
import gi
import glob
import json
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

# Global variables
windows = []
open_notes = {}
manager_instance = None
data_dir = os.path.expanduser("~/.sticky_notes")
os.makedirs(data_dir, exist_ok=True)
session_file = os.path.join(data_dir, "session.json")

# Default colors
DEFAULT_COLORS = [
    "#FFF9C4",  # Yellow
    "#C8E6C9",  # Green
    "#BBDEFB",  # Blue
    "#FFCCBC",  # Orange
    "#E1BEE7",  # Purple
]

def on_window_destroy(window):
    global windows
    if window in windows:
        windows.remove(window)
    if isinstance(window, StickyNote) and window.note_id in open_notes:
        del open_notes[window.note_id]
    if not windows:
        save_session()
        Gtk.main_quit()

def save_session():
    session_data = []
    for window in windows:
        if isinstance(window, StickyNote):
            # Save window position
            pos = window.get_position()
            session_data.append({
                "note_id": window.note_id,
                "x": pos.root_x,
                "y": pos.root_y
            })
    
    with open(session_file, 'w') as f:
        json.dump(session_data, f)

def load_session():
    if not os.path.exists(session_file):
        return []
    
    try:
        with open(session_file, 'r') as f:
            return json.load(f)
    except:
        return []

class NoteManager(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sticky Notes Manager")
        self.set_default_size(300, 400)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Main container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.add(box)
        
        # New Note button
        new_btn = Gtk.Button(label="New Note")
        new_btn.connect("clicked", self.new_note)
        box.pack_start(new_btn, False, False, 0)
        
        # List of notes
        scrolled = Gtk.ScrolledWindow()
        self.listbox = Gtk.ListBox()
        scrolled.add(self.listbox)
        box.pack_start(scrolled, True, True, 0)
        
        # Load existing notes
        self.load_notes()
        
        # Connect signals
        self.listbox.connect("row-activated", self.on_row_activated)
        
        # Add to global windows list
        global windows
        windows.append(self)
        self.connect("destroy", self.on_manager_destroy)
    
    def on_manager_destroy(self, widget):
        global manager_instance
        manager_instance = None
    
    def load_notes(self):
        # Clear existing items
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        
        # Scan for note folders
        note_folders = glob.glob(os.path.join(data_dir, "note*"))
        note_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        for folder in note_folders:
            note_id = os.path.basename(folder)
            note_path = os.path.join(folder, "text.md")
            if os.path.exists(note_path):
                with open(note_path, 'r') as f:
                    first_line = f.readline().strip()
                    title = first_line if first_line else "Untitled"
                
                # Get note color
                color_path = os.path.join(folder, "color.txt")
                color = DEFAULT_COLORS[0]  # Default yellow
                if os.path.exists(color_path):
                    with open(color_path, 'r') as f:
                        color = f.read().strip()
                
                row = Gtk.ListBoxRow()
                hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
                row.add(hbox)
                
                # Color indicator
                color_box = Gtk.DrawingArea()
                color_box.set_size_request(20, 20)
                color_box.connect("draw", self.draw_color_box, color)
                hbox.pack_start(color_box, False, False, 5)
                
                label = Gtk.Label(label=title, xalign=0)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                hbox.pack_start(label, True, True, 0)
                
                # Store note_id in the row
                row.note_id = note_id
                self.listbox.add(row)
        
        self.listbox.show_all()
    
    def draw_color_box(self, widget, cr, color):
        # Parse color
        rgba = Gdk.RGBA()
        rgba.parse(color)
        
        # Draw colored circle
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(10, 10, 8, 0, 2 * 3.14159)
        cr.fill()
    
    def new_note(self, button):
        # Find next available note ID
        existing = []
        for d in os.listdir(data_dir):
            if os.path.isdir(os.path.join(data_dir, d)) and d.startswith("note"):
                try:
                    num = int(d[4:])
                    existing.append(num)
                except ValueError:
                    continue
        
        next_id = max(existing) + 1 if existing else 1
        note_id = f"note{next_id}"
        
        # Create note folder
        note_dir = os.path.join(data_dir, note_id)
        os.makedirs(note_dir, exist_ok=True)
        
        # Create default content
        note_path = os.path.join(note_dir, "text.md")
        with open(note_path, 'w') as f:
            f.write("New Note\n\n")
        
        # Save default color
        color_path = os.path.join(note_dir, "color.txt")
        with open(color_path, 'w') as f:
            f.write(DEFAULT_COLORS[0])
        
        # Open the new note
        self.open_note(note_id)
        self.load_notes()
    
    def open_note(self, note_id):
        global open_notes
        if note_id in open_notes:
            open_notes[note_id].present()  # Bring to front if already open
            return
        
        note = StickyNote(note_id)
        note.show_all()
        open_notes[note_id] = note
    
    def on_row_activated(self, listbox, row):
        self.open_note(row.note_id)

class StickyNote(Gtk.Window):
    def __init__(self, note_id):
        self.note_id = note_id
        super().__init__(title="Sticky Note")
        self.set_default_size(400, 300)
        self.set_border_width(10)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        # Timeout tracking
        self.timeout_id = None
        
        # Setup UI
        self.setup_ui()
        
        # Load content and color
        self.load_content()
        
        # Connect signals
        self.connect("delete-event", self.on_close)
        self.text_buffer.connect("changed", self.on_text_changed)
        
        # Add to global windows list
        global windows, open_notes
        windows.append(self)
        open_notes[note_id] = self
        self.connect("destroy", self.on_note_destroy)
    
    def on_note_destroy(self, widget):
        # Clean up any pending timeouts
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
        # Call global handler
        on_window_destroy(widget)
    
    def setup_ui(self):
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.add(main_box)
        
        # Header bar for actions
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "Sticky Note"
        self.set_titlebar(header)
        
        # Menu button
        menu_button = Gtk.MenuButton()
        menu_icon = Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        menu_button.add(menu_icon)
        header.pack_end(menu_button)
        
        # Menu
        menu = Gtk.Menu()
        menu_button.set_popup(menu)
        
        # Show all notes item
        show_all_item = Gtk.MenuItem(label="Show All Notes")
        show_all_item.connect("activate", self.show_manager)
        menu.append(show_all_item)
        
        # Change color item
        color_item = Gtk.MenuItem(label="Change Color")
        color_item.connect("activate", self.change_color)
        menu.append(color_item)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # Close item
        close_item = Gtk.MenuItem(label="Close")
        close_item.connect("activate", lambda x: self.destroy())
        menu.append(close_item)
        
        menu.show_all()
        
        # Tab bar
        self.tabbar = Gtk.Notebook()
        self.tabbar.set_scrollable(True)
        main_box.pack_start(self.tabbar, True, True, 0)
        
        # Editor
        editor_scroll = Gtk.ScrolledWindow()
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_buffer = self.text_view.get_buffer()
        editor_scroll.add(self.text_view)
        self.tabbar.append_page(editor_scroll, Gtk.Label(label="Edit"))
        
        # Preview
        preview_scroll = Gtk.ScrolledWindow()
        self.preview_view = Gtk.TextView()
        self.preview_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.preview_view.set_editable(False)
        self.preview_view.set_cursor_visible(False)
        self.preview_buffer = self.preview_view.get_buffer()
        preview_scroll.add(self.preview_view)
        self.tabbar.append_page(preview_scroll, Gtk.Label(label="Preview"))
        
        # Configure tags for formatting
        self.setup_text_tags()
    
    def setup_text_tags(self):
        # Create text tags for formatting
        tag_table = self.preview_buffer.get_tag_table()
        
        # Bold tag
        self.bold_tag = Gtk.TextTag(name="bold")
        self.bold_tag.set_property("weight", Pango.Weight.BOLD)
        tag_table.add(self.bold_tag)
        
        # Italic tag
        self.italic_tag = Gtk.TextTag(name="italic")
        self.italic_tag.set_property("style", Pango.Style.ITALIC)
        tag_table.add(self.italic_tag)
        
        # Header tag
        self.header_tag = Gtk.TextTag(name="header")
        self.header_tag.set_property("weight", Pango.Weight.BOLD)
        self.header_tag.set_property("scale", 1.5)
        tag_table.add(self.header_tag)
        
        # Code tag
        self.code_tag = Gtk.TextTag(name="code")
        self.code_tag.set_property("family", "Monospace")
        self.code_tag.set_property("background", "#E0E0E0")
        tag_table.add(self.code_tag)
        
        # Link tag
        self.link_tag = Gtk.TextTag(name="link")
        self.link_tag.set_property("foreground", "blue")
        self.link_tag.set_property("underline", Pango.Underline.SINGLE)
        tag_table.add(self.link_tag)
    
    def get_note_path(self):
        return os.path.join(data_dir, self.note_id, "text.md")
    
    def get_color_path(self):
        return os.path.join(data_dir, self.note_id, "color.txt")
    
    def load_content(self):
        note_path = self.get_note_path()
        color_path = self.get_color_path()
        
        # Load color
        color = DEFAULT_COLORS[0]  # Default yellow
        if os.path.exists(color_path):
            with open(color_path, 'r') as f:
                color = f.read().strip()
        
        # Apply color
        self.apply_color(color)
        
        # Load content
        if os.path.exists(note_path):
            with open(note_path, 'r') as f:
                content = f.read()
                self.text_buffer.set_text(content)
                self.update_preview()
                # Set window title from first line
                lines = content.splitlines()
                if lines:
                    self.set_title(lines[0] or "Untitled")
    
    def apply_color(self, color):
        # Create CSS for the note
        css = f"""
        * {{
            background-color: {color};
            font-family: 'Sans Serif';
        }}
        GtkTextView, GtkTextView text {{
            background-color: {color};
            font-size: 11pt;
        }}
        GtkScrolledWindow {{
            background-color: {color};
        }}
        """.encode('utf-8')
        
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        
        # Apply to this window only
        context = self.get_style_context()
        context.add_provider(style_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Also apply directly to text views as a fallback
        rgba = Gdk.RGBA()
        rgba.parse(color)
        self.text_view.override_background_color(Gtk.StateFlags.NORMAL, rgba)
        self.preview_view.override_background_color(Gtk.StateFlags.NORMAL, rgba)
    
    def update_preview(self):
        # Get text from editor
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        text = self.text_buffer.get_text(start_iter, end_iter, True)
        
        # Clear preview
        self.preview_buffer.set_text("")
        
        # Simple markdown parsing
        lines = text.split('\n')
        in_code_block = False
        
        for line in lines:
            start = self.preview_buffer.get_end_iter()
            
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            
            if in_code_block:
                self.preview_buffer.insert_with_tags(start, line + "\n", self.code_tag)
                continue
            
            # Headers
            if line.startswith("# "):
                self.preview_buffer.insert_with_tags(start, line[2:] + "\n", self.header_tag)
            elif line.startswith("## "):
                self.preview_buffer.insert_with_tags(start, line[3:] + "\n", self.header_tag)
            elif line.startswith("### "):
                self.preview_buffer.insert_with_tags(start, line[4:] + "\n", self.header_tag)
            # Bold and italic
            elif "**" in line or "__" in line or "*" in line or "_" in line:
                self.parse_inline_formatting(line)
            # Default text
            else:
                self.preview_buffer.insert(start, line + "\n")
    
    def parse_inline_formatting(self, line):
        # Simple regex for bold and italic
        pos = 0
        start = self.preview_buffer.get_end_iter()
        
        while pos < len(line):
            # Bold with **
            if line.startswith("**", pos):
                end_pos = line.find("**", pos+2)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+2:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.bold_tag, len(line[pos+2:end_pos]))
                    pos = end_pos + 2
                    continue
            
            # Bold with __
            if line.startswith("__", pos):
                end_pos = line.find("__", pos+2)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+2:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.bold_tag, len(line[pos+2:end_pos]))
                    pos = end_pos + 2
                    continue
            
            # Italic with *
            if line.startswith("*", pos) and not line.startswith("**", pos):
                end_pos = line.find("*", pos+1)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+1:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.italic_tag, len(line[pos+1:end_pos]))
                    pos = end_pos + 1
                    continue
            
            # Italic with _
            if line.startswith("_", pos) and not line.startswith("__", pos):
                end_pos = line.find("_", pos+1)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+1:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.italic_tag, len(line[pos+1:end_pos]))
                    pos = end_pos + 1
                    continue
            
            # Regular text
            self.preview_buffer.insert(start, line[pos])
            start = self.preview_buffer.get_end_iter()
            pos += 1
        
        self.preview_buffer.insert(start, "\n")
    
    def apply_tag_to_last(self, tag, length):
        end_iter = self.preview_buffer.get_end_iter()
        start_iter = end_iter.copy()
        start_iter.backward_chars(length)
        self.preview_buffer.apply_tag(tag, start_iter, end_iter)
    
    def on_text_changed(self, buffer):
        # Update window title from first line
        start_iter = buffer.get_start_iter()
        end_iter = start_iter.copy()
        if not end_iter.ends_line():
            end_iter.forward_to_line_end()
        first_line = buffer.get_text(start_iter, end_iter, False)
        self.set_title(first_line or "Untitled")
        
        self.update_preview()
        
        # Cancel any pending save
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
        
        # Schedule new save
        self.timeout_id = GLib.timeout_add_seconds(2, self.save_content)
    
    def save_content(self):
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        text = self.text_buffer.get_text(start_iter, end_iter, True)
        
        note_path = self.get_note_path()
        os.makedirs(os.path.dirname(note_path), exist_ok=True)
        with open(note_path, 'w') as f:
            f.write(text)
        
        self.timeout_id = None
        return False  # Disconnect timeout
    
    def on_close(self, window, event):
        self.save_content()
        return False  # Propagate event further
    
    def show_manager(self, widget):
        global manager_instance
        if manager_instance is None:
            manager_instance = NoteManager()
            manager_instance.show_all()
        else:
            manager_instance.present()  # Bring to front
    
    def change_color(self, widget):
        dialog = Gtk.ColorChooserDialog(title="Choose Note Color", parent=self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            color = dialog.get_rgba()
            # Convert to hex string
            hex_color = self.rgba_to_hex(color)
            
            # Save color
            color_path = self.get_color_path()
            with open(color_path, 'w') as f:
                f.write(hex_color)
            
            # Apply new color
            self.apply_color(hex_color)
        dialog.destroy()
    
    def rgba_to_hex(self, rgba):
        r = int(rgba.red * 255)
        g = int(rgba.green * 255)
        b = int(rgba.blue * 255)
        return f"#{r:02x}{g:02x}{b:02x}"

def open_session_notes():
    session_data = load_session()
    notes = []
    
    for entry in session_data:
        note_id = entry["note_id"]
        note_dir = os.path.join(data_dir, note_id)
        if os.path.exists(note_dir):
            note = StickyNote(note_id)
            # Restore position
            note.move(entry["x"], entry["y"])
            note.show_all()
            notes.append(note)
    
    return notes

if __name__ == "__main__":
    # Try to open notes from last session
    session_notes = open_session_notes()
    
    if session_notes:
        # We have notes from last session
        Gtk.main()
    else:
        # No session found - open latest note or create new
        note_folders = glob.glob(os.path.join(data_dir, "note*"))
        if note_folders:
            # Open the latest note
            note_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            note_id = os.path.basename(note_folders[0])
            note = StickyNote(note_id)
            note.show_all()
            Gtk.main()
        else:
            # Create a new note
            note_id = "note1"
            note_dir = os.path.join(data_dir, note_id)
            os.makedirs(note_dir, exist_ok=True)
            
            # Create default content
            note_path = os.path.join(note_dir, "text.md")
            with open(note_path, 'w') as f:
                f.write("New Note\n\n")
            
            # Save default color
            color_path = os.path.join(note_dir, "color.txt")
            with open(color_path, 'w') as f:
                f.write(DEFAULT_COLORS[0])
            
            # Open the new note
            note = StickyNote(note_id)
            note.show_all()
            Gtk.main()