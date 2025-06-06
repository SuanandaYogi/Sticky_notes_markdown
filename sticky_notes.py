#!/usr/bin/env python3
import os
import warnings
import re
import unicodedata

# Suppress GTK deprecation warnings (StatusIcon is deprecated but still functional)
warnings.filterwarnings("ignore", ".*is deprecated", DeprecationWarning)

import gi
import glob
import json
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

# Try to import system tray support
HAS_INDICATOR = False
HAS_STATUS_ICON = False

try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as appindicator
    HAS_INDICATOR = True
except (ImportError, ValueError):
    try:
        # Fallback to older StatusIcon (works on more systems)
        from gi.repository import Gtk
        HAS_STATUS_ICON = True
    except ImportError:
        pass

# Icon fallback system for OS compatibility
def get_available_icon(icon_names):
    """Try multiple icon names and return the first available one"""
    icon_theme = Gtk.IconTheme.get_default()
    for icon_name in icon_names:
        if icon_theme.has_icon(icon_name):
            return icon_name
    return icon_names[-1]  # Fallback to last option

# Icon constants with fallbacks
APP_ICON_NAMES = [
    "accessories-text-editor",
    "text-editor",
    "text-x-generic",
    "document-edit",
    "note",
    "sticky-notes",
    "text-x-script",
    "application-default-icon"
]

MENU_ICON_NAMES = [
    "open-menu-symbolic",
    "view-more-symbolic",
    "hamburger-menu",
    "application-menu",
    "preferences-system",
    "view-more"
]

ZOOM_IN_ICONS = [
    "zoom-in-symbolic",
    "zoom-in",
    "list-add-symbolic",
    "add",
    "gtk-zoom-in"
]

ZOOM_OUT_ICONS = [
    "zoom-out-symbolic",
    "zoom-out",
    "list-remove-symbolic",
    "remove",
    "gtk-zoom-out"
]

# Global variables
windows = []
open_notes = {}
manager_instance = None
tray_icon = None
data_dir = os.path.expanduser("~/.sticky_notes")
os.makedirs(data_dir, exist_ok=True)
session_file = os.path.join(data_dir, "session.json")

# Very light/whitish pastel colors
DEFAULT_COLORS = [
    "#FEFEFE",  # Almost white
    "#FFF8F8",  # Very light pink
    "#FFF9F0",  # Very light cream
    "#FFFEF8",  # Very light yellow
    "#F8FFF8",  # Very light green
    "#F8F9FF",  # Very light blue
    "#F9F8FF",  # Very light lavender
    "#FFF8FC",  # Very light rose
]

def refresh_manager():
    """Refresh the notes manager if it exists and is visible"""
    global manager_instance
    if manager_instance and manager_instance.get_visible():
        manager_instance.load_notes()

def on_window_destroy(window):
    global windows
    if window in windows:
        windows.remove(window)
    if isinstance(window, StickyNote) and window.note_id in open_notes:
        del open_notes[window.note_id]
    # Refresh manager when a note window is closed
    refresh_manager()
    # Don't quit if we have system tray or manager
    if not windows and not tray_icon and not manager_instance:
        save_session()
        Gtk.main_quit()
    elif not windows:
        save_session()

def save_session():
    session_data = []
    for window in windows:
        if isinstance(window, StickyNote):
            pos = window.get_position()
            size = window.get_size()
            session_data.append({
                "note_id": window.note_id,
                "x": pos.root_x,
                "y": pos.root_y,
                "width": size.width,
                "height": size.height,
                "is_edit_mode": window.is_edit_mode,
                "zoom_level": window.zoom_level
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

def create_system_tray():
    global tray_icon
    app_icon = get_available_icon(APP_ICON_NAMES)
    if HAS_INDICATOR:
        # Use AppIndicator3 (Unity, some GNOME)
        tray_icon = appindicator.Indicator.new(
            "sticky-notes",
            app_icon,
            appindicator.IndicatorCategory.APPLICATION_STATUS
        )
        tray_icon.set_status(appindicator.IndicatorStatus.ACTIVE)
        menu = create_tray_menu()
        tray_icon.set_menu(menu)
    elif HAS_STATUS_ICON:
        # Use older StatusIcon (works on XFCE, MATE, etc.)
        # Suppress deprecation warnings for this block
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            tray_icon = Gtk.StatusIcon()
            tray_icon.set_from_icon_name(app_icon)
            tray_icon.set_tooltip_text("Sticky Notes")
            tray_icon.connect("popup-menu", on_status_icon_popup)
            tray_icon.connect("activate", lambda x: show_manager())
    return tray_icon

def create_tray_menu():
    menu = Gtk.Menu()
    # New note
    new_item = Gtk.MenuItem(label="New Note")
    new_item.connect("activate", lambda x: create_new_note())
    menu.append(new_item)
    # Show all notes
    show_all_item = Gtk.MenuItem(label="Show All Notes")
    show_all_item.connect("activate", lambda x: show_manager())
    menu.append(show_all_item)
    # Separator
    menu.append(Gtk.SeparatorMenuItem())
    # Exit
    exit_item = Gtk.MenuItem(label="Exit")
    exit_item.connect("activate", lambda x: exit_app())
    menu.append(exit_item)
    menu.show_all()
    return menu

def on_status_icon_popup(status_icon, button, activate_time):
    menu = create_tray_menu()
    menu.popup(None, None, Gtk.StatusIcon.position_menu, status_icon, button, activate_time)

def create_new_note():
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
    # Save default zoom
    zoom_path = os.path.join(note_dir, "zoom.txt")
    with open(zoom_path, 'w') as f:
        f.write("1.0")
    # Create and show the note in edit mode
    note = StickyNote(note_id)
    note.show_all()
    note.is_edit_mode = True
    note.notebook.set_current_page(1)  # Edit mode
    note.update_edit_button()
    note.text_view.grab_focus()
    
    # Refresh manager
    refresh_manager()

def show_manager():
    global manager_instance
    if manager_instance is None:
        manager_instance = NoteManager()
        manager_instance.show_all()
    else:
        manager_instance.present()
    # Refresh when showing the manager
    manager_instance.load_notes()

def delete_note(note_id):
    # Close note window if open
    if note_id in open_notes:
        open_notes[note_id].destroy()
    # Delete note files
    note_dir = os.path.join(data_dir, note_id)
    if os.path.exists(note_dir):
        import shutil
        shutil.rmtree(note_dir)
    # Refresh manager
    refresh_manager()

def exit_app():
    global tray_icon, manager_instance
    save_session()
    # Save dimensions of all windows before exiting
    for window in windows:
        if isinstance(window, StickyNote):
            window.save_window_dimensions()
    if tray_icon:
        if HAS_STATUS_ICON and hasattr(tray_icon, 'set_visible'):
            tray_icon.set_visible(False)
        tray_icon = None
    if manager_instance:
        manager_instance.destroy()
        manager_instance = None
    Gtk.main_quit()

class NoteManager(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sticky Notes Manager")
        self.set_default_size(400, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        # Use OS-friendly icon
        app_icon = get_available_icon(APP_ICON_NAMES)
        self.set_icon_name(app_icon)
        # Hide from taskbar and alt-tab
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        # Sort preference
        self.sort_by_name = False
        # Track if this is the first load
        self.first_load = True
        # Main container
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self.add(box)
        # Header
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        box.pack_start(header_box, False, False, 0)
        # New Note button
        new_btn = Gtk.Button(label="New Note")
        new_btn.connect("clicked", lambda x: create_new_note())
        header_box.pack_start(new_btn, True, True, 0)
        # Sort button
        self.sort_btn = Gtk.Button(label="Sort: Date")
        self.sort_btn.connect("clicked", self.toggle_sort)
        header_box.pack_start(self.sort_btn, False, False, 0)
        # Hide to tray button (if tray is available)
        if tray_icon:
            hide_btn = Gtk.Button(label="Hide to Tray")
            hide_btn.connect("clicked", lambda x: self.hide())
            header_box.pack_start(hide_btn, False, False, 0)
        # List of notes
        scrolled = Gtk.ScrolledWindow()
        self.listbox = Gtk.ListBox()
        scrolled.add(self.listbox)
        box.pack_start(scrolled, True, True, 0)
        # Status bar
        self.status_bar = Gtk.Statusbar()
        self.status_context = self.status_bar.get_context_id("info")
        box.pack_start(self.status_bar, False, False, 0)
        # Connect signals
        self.listbox.connect("row-activated", self.on_row_activated)
        self.listbox.connect("button-press-event", self.on_listbox_button_press)
        # Add to global windows list
        global windows
        windows.append(self)
        self.connect("destroy", self.on_manager_destroy)
        self.connect("delete-event", self.on_delete_event)
        self.connect("show", self.on_show)  # Load notes when window is shown
        # Load existing notes immediately (for first time)
        self.load_notes()
    
    def on_show(self, widget):
        """Called when window is shown - ensures notes are loaded"""
        # Small delay to ensure window is fully realized
        GLib.idle_add(self.load_notes)
    
    def on_delete_event(self, widget, event):
        return False  # Allow destruction
    
    def on_manager_destroy(self, widget):
        global manager_instance
        manager_instance = None
    
    def on_listbox_button_press(self, widget, event):
        # Right click for context menu
        if event.button == 3:  # Right mouse button
            row = widget.get_row_at_y(int(event.y))
            if row and hasattr(row, 'note_id'):
                widget.select_row(row)
                self.show_context_menu(event, row.note_id)
            return True
        return False
    
    def show_context_menu(self, event, note_id):
        menu = Gtk.Menu()
        # Open
        open_item = Gtk.MenuItem(label="Open")
        open_item.connect("activate", lambda x: self.open_note(note_id))
        menu.append(open_item)
        # Delete
        delete_item = Gtk.MenuItem(label="Delete")
        delete_item.connect("activate", lambda x: self.confirm_delete(note_id))
        menu.append(delete_item)
        menu.show_all()
        menu.popup(None, None, None, None, event.button, event.time)
    
    def confirm_delete(self, note_id):
        # Get note title for confirmation
        note_path = os.path.join(data_dir, note_id, "text.md")
        title = "Untitled"
        if os.path.exists(note_path):
            try:
                with open(note_path, 'r') as f:
                    first_line = f.readline().strip()
                    title = first_line if first_line else "Untitled"
            except:
                pass
        # Updated MessageDialog constructor to avoid deprecation warnings
        dialog = Gtk.MessageDialog(
            parent=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete note '{title}'?"
        )
        dialog.format_secondary_text("This action cannot be undone.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            delete_note(note_id)
    
    def open_note(self, note_id):
        if note_id in open_notes:
            # Bring existing note to front
            note = open_notes[note_id]
            note.show()
            note.present()
            # Apply saved dimensions
            note.load_window_dimensions()
        else:
            # Create new note window
            note = StickyNote(note_id)
            note.show_all()
        # Refresh manager to show updated status
        self.load_notes()
    
    def toggle_sort(self, button):
        self.sort_by_name = not self.sort_by_name
        if self.sort_by_name:
            self.sort_btn.set_label("Sort: Name")
        else:
            self.sort_btn.set_label("Sort: Date")
        self.load_notes()
    
    def load_notes(self):
        # Always load on first time, or only if visible after that
        if not self.first_load and not self.get_visible():
            return
        self.first_load = False
        # Remember current selection
        selected_row = self.listbox.get_selected_row()
        selected_note_id = None
        if selected_row and hasattr(selected_row, 'note_id'):
            selected_note_id = selected_row.note_id
        # Clear existing items
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        # Scan for note folders
        note_folders = glob.glob(os.path.join(data_dir, "note*"))
        if self.sort_by_name:
            def get_note_title(folder):
                note_path = os.path.join(folder, "text.md")
                if os.path.exists(note_path):
                    try:
                        with open(note_path, 'r') as f:
                            first_line = f.readline().strip()
                            return first_line if first_line else "Untitled"
                    except:
                        pass
                return "Untitled"
            note_folders.sort(key=get_note_title)
        else:
            note_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        open_count = 0
        total_count = 0
        for folder in note_folders:
            note_id = os.path.basename(folder)
            note_path = os.path.join(folder, "text.md")
            if os.path.exists(note_path):
                total_count += 1
                try:
                    with open(note_path, 'r') as f:
                        first_line = f.readline().strip()
                        title = first_line if first_line else "Untitled"
                except:
                    title = "Untitled"
                # Get note color
                color_path = os.path.join(folder, "color.txt")
                color = DEFAULT_COLORS[0]
                if os.path.exists(color_path):
                    try:
                        with open(color_path, 'r') as f:
                            color = f.read().strip()
                    except:
                        pass
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
                # Status indicator
                status_label = Gtk.Label()
                if note_id in open_notes:
                    status_label.set_text("●")
                    status_label.set_tooltip_text("Currently open")
                    open_count += 1
                else:
                    status_label.set_text("○")
                hbox.pack_start(status_label, False, False, 0)
                row.note_id = note_id
                self.listbox.add(row)
                if note_id == selected_note_id:
                    self.listbox.select_row(row)
        # Update status bar
        self.status_bar.pop(self.status_context)
        self.status_bar.push(self.status_context, f"{open_count} open, {total_count} total notes")
        self.listbox.show_all()
    
    def draw_color_box(self, widget, cr, color):
        rgba = Gdk.RGBA()
        rgba.parse(color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)
        cr.arc(10, 10, 8, 0, 2 * 3.14159)
        cr.fill()
        # Add a subtle border to make very light colors visible
        cr.set_source_rgba(0.8, 0.8, 0.8, 0.5)
        cr.set_line_width(1)
        cr.arc(10, 10, 8, 0, 2 * 3.14159)
        cr.stroke()
    
    def on_row_activated(self, listbox, row):
        if hasattr(row, 'note_id'):
            self.open_note(row.note_id)

class TableParser:
    """Enhanced table parser for markdown tables with proper emoji/symbol support"""
    @staticmethod
    def is_table_line(line):
        """Check if a line is part of a table"""
        stripped = line.strip()
        return (stripped.startswith('|') and stripped.endswith('|') and
                stripped.count('|') >= 2)
    
    @staticmethod
    def is_separator_line(line):
        """Check if a line is a table separator (header divider)"""
        stripped = line.strip()
        if not TableParser.is_table_line(line):
            return False
        # Remove outer pipes and split
        content = stripped[1:-1]
        cells = content.split('|')
        # Check if all cells contain only dashes, spaces, and colons
        for cell in cells:
            cell = cell.strip()
            if not cell:
                continue
            if not re.match(r'^:?-+:?$', cell):
                return False
        return True
    
    @staticmethod
    def parse_table_cells(line):
        """Parse a table line into cells"""
        stripped = line.strip()
        if not stripped.startswith('|') or not stripped.endswith('|'):
            return []
        # Remove outer pipes and split
        content = stripped[1:-1]
        cells = [cell.strip() for cell in content.split('|')]
        return cells
    
    @staticmethod
    def get_column_alignments(separator_line):
        """Parse column alignments from separator line"""
        cells = TableParser.parse_table_cells(separator_line)
        alignments = []
        for cell in cells:
            cell = cell.strip()
            if cell.startswith(':') and cell.endswith(':'):
                alignments.append('center')
            elif cell.endswith(':'):
                alignments.append('right')
            else:
                alignments.append('left')
        return alignments
    
    @staticmethod
    def estimate_display_width(text):
        """Estimate the display width of text including emojis and special characters"""
        if not text:
            return 0
        # Remove markdown formatting for width calculation only
        clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        clean = re.sub(r'\*([^*]+)\*', r'\1', clean)
        width = 0
        for char in clean:
            # Get Unicode category
            category = unicodedata.category(char)
            # Emoji and symbols usually take more space
            if category.startswith('So'):  # Other symbols (including emojis)
                width += 2  # Emojis typically take 2 character widths
            elif category.startswith('Sm'):  # Math symbols
                width += 1.5  # Math symbols slightly wider
            elif category.startswith('Sc'):  # Currency symbols
                width += 1.5
            elif unicodedata.east_asian_width(char) in ('F', 'W'):  # Full-width or Wide
                width += 2
            else:
                width += 1
        return int(width)
    
    @staticmethod
    def pad_text(text, width, align='left'):
        """Pad text to specified width while preserving original content"""
        current_width = TableParser.estimate_display_width(text)
        padding_needed = max(0, width - current_width)
        if align == 'center':
            left_pad = padding_needed // 2
            right_pad = padding_needed - left_pad
            return ' ' * left_pad + text + ' ' * right_pad
        elif align == 'right':
            return ' ' * padding_needed + text
        else:  # left align
            return text + ' ' * padding_needed
    
    @staticmethod
    def format_table(lines):
        """Format table lines into a nice display preserving all symbols and emojis"""
        if not lines:
            return ""
        # Parse all rows
        header_cells = TableParser.parse_table_cells(lines[0])
        if len(lines) < 2:
            return ""
        # Check if second line is separator
        separator_idx = 1
        alignments = ['left'] * len(header_cells)
        data_start = 1
        if TableParser.is_separator_line(lines[1]):
            alignments = TableParser.get_column_alignments(lines[1])
            data_start = 2
        # Parse data rows
        data_rows = []
        for i in range(data_start, len(lines)):
            if TableParser.is_table_line(lines[i]):
                data_rows.append(TableParser.parse_table_cells(lines[i]))
        # Ensure all rows have the same number of columns
        max_cols = len(header_cells)
        for row in data_rows:
            max_cols = max(max_cols, len(row))
        # Pad rows to have same number of columns
        while len(header_cells) < max_cols:
            header_cells.append("")
        while len(alignments) < max_cols:
            alignments.append('left')
        for row in data_rows:
            while len(row) < max_cols:
                row.append("")
        # Calculate column widths using estimated display width
        all_rows = [header_cells] + data_rows
        col_widths = []
        for col_idx in range(max_cols):
            max_width = 0
            for row in all_rows:
                if col_idx < len(row):
                    estimated_width = TableParser.estimate_display_width(row[col_idx])
                    max_width = max(max_width, estimated_width)
            col_widths.append(max(max_width, 3))  # Minimum width of 3
        # Format the table
        result = []
        # Top border
        border_parts = []
        for width in col_widths:
            border_parts.append('─' * (width + 2))
        result.append('┌' + '┬'.join(border_parts) + '┐')
        # Header row
        header_parts = []
        for i, (cell, width, align) in enumerate(zip(header_cells, col_widths, alignments)):
            formatted_cell = TableParser.pad_text(cell, width, align)
            header_parts.append(f' {formatted_cell} ')
        result.append('│' + '│'.join(header_parts) + '│')
        # Header separator
        sep_parts = []
        for width in col_widths:
            sep_parts.append('─' * (width + 2))
        result.append('├' + '┼'.join(sep_parts) + '┤')
        # Data rows
        for row in data_rows:
            row_parts = []
            for i, width in enumerate(col_widths):
                cell = row[i] if i < len(row) else ""
                align = alignments[i] if i < len(alignments) else 'left'
                formatted_cell = TableParser.pad_text(cell, width, align)
                row_parts.append(f' {formatted_cell} ')
            result.append('│' + '│'.join(row_parts) + '│')
        # Bottom border
        border_parts = []
        for width in col_widths:
            border_parts.append('─' * (width + 2))
        result.append('└' + '┴'.join(border_parts) + '┘')
        return '\n'.join(result)

class StickyNote(Gtk.Window):
    def __init__(self, note_id):
        self.note_id = note_id
        self.zoom_level = 1.0  # Initialize zoom level
        super().__init__()
        self.set_default_size(400, 300)
        self.set_position(Gtk.WindowPosition.CENTER)
        # Use OS-friendly icon
        app_icon = get_available_icon(APP_ICON_NAMES)
        self.set_icon_name(app_icon)
        # Hide from taskbar and alt-tab
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        # Timeout tracking
        self.timeout_id = None
        self.is_edit_mode = False
        # Setup UI
        self.setup_ui()
        # Load saved window dimensions
        self.load_window_dimensions()
        # Load content, color, and zoom
        self.load_content()
        self.load_zoom_level()
        # Connect signals
        self.connect("delete-event", self.on_close)
        self.connect("key-press-event", self.on_key_press)  # Add keyboard shortcuts
        self.connect("configure-event", self.on_configure_event)  # Save window size/position
        self.text_buffer.connect("changed", self.on_text_changed)
        # Add to global windows list
        global windows, open_notes
        windows.append(self)
        open_notes[note_id] = self
        self.connect("destroy", self.on_note_destroy)
    
    def on_configure_event(self, widget, event):
        """Save window dimensions when moved or resized"""
        self.save_window_dimensions()
        return False
    
    def get_dimensions_path(self):
        return os.path.join(data_dir, self.note_id, "dimensions.json")
    
    def save_window_dimensions(self):
        """Save current window position and size"""
        pos = self.get_position()
        size = self.get_size()
        dimensions = {
            "x": pos.root_x,
            "y": pos.root_y,
            "width": size.width,
            "height": size.height
        }
        dimensions_path = self.get_dimensions_path()
        try:
            with open(dimensions_path, 'w') as f:
                json.dump(dimensions, f)
        except:
            pass
    
    def load_window_dimensions(self):
        """Load and apply saved window dimensions"""
        dimensions_path = self.get_dimensions_path()
        if os.path.exists(dimensions_path):
            try:
                with open(dimensions_path, 'r') as f:
                    dimensions = json.load(f)
                # Apply position
                if "x" in dimensions and "y" in dimensions:
                    self.move(dimensions["x"], dimensions["y"])
                # Apply size
                if "width" in dimensions and "height" in dimensions:
                    self.resize(dimensions["width"], dimensions["height"])
            except:
                pass
    
    def on_note_destroy(self, widget):
        if self.timeout_id is not None:
            GLib.source_remove(self.timeout_id)
        on_window_destroy(widget)
    
    def setup_ui(self):
        # Header bar
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = "Sticky Note"
        self.set_titlebar(header)
        # Zoom controls in header
        zoom_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.pack_start(zoom_box)
        # Zoom out button
        zoom_out_btn = Gtk.Button()
        zoom_out_icon = get_available_icon(ZOOM_OUT_ICONS)
        zoom_out_btn.add(Gtk.Image.new_from_icon_name(zoom_out_icon, Gtk.IconSize.BUTTON))
        zoom_out_btn.set_tooltip_text("Zoom Out (Ctrl+-)")
        zoom_out_btn.connect("clicked", self.zoom_out)
        zoom_box.pack_start(zoom_out_btn, False, False, 0)
        # Zoom level label
        self.zoom_label = Gtk.Label("100%")
        self.zoom_label.set_margin_left(5)
        self.zoom_label.set_margin_right(5)
        zoom_box.pack_start(self.zoom_label, False, False, 0)
        # Zoom in button  
        zoom_in_btn = Gtk.Button()
        zoom_in_icon = get_available_icon(ZOOM_IN_ICONS)
        zoom_in_btn.add(Gtk.Image.new_from_icon_name(zoom_in_icon, Gtk.IconSize.BUTTON))
        zoom_in_btn.set_tooltip_text("Zoom In (Ctrl++)")
        zoom_in_btn.connect("clicked", self.zoom_in)
        zoom_box.pack_start(zoom_in_btn, False, False, 0)
        # Reset zoom button
        reset_zoom_btn = Gtk.Button("Reset")
        reset_zoom_btn.set_tooltip_text("Reset Zoom (Ctrl+0)")
        reset_zoom_btn.connect("clicked", self.reset_zoom)
        zoom_box.pack_start(reset_zoom_btn, False, False, 0)
        # Menu button
        menu_button = Gtk.MenuButton()
        menu_icon = get_available_icon(MENU_ICON_NAMES)
        menu_button.add(Gtk.Image.new_from_icon_name(menu_icon, Gtk.IconSize.BUTTON))
        header.pack_end(menu_button)
        # Menu
        menu = Gtk.Menu()
        menu_button.set_popup(menu)
        # Edit/Preview toggle
        self.edit_item = Gtk.MenuItem(label="Edit")
        self.edit_item.connect("activate", self.toggle_edit_mode)
        menu.append(self.edit_item)
        # Show manager
        manager_item = Gtk.MenuItem(label="Show All Notes")
        manager_item.connect("activate", lambda x: show_manager())
        menu.append(manager_item)
        # Change color
        color_item = Gtk.MenuItem(label="Change Color")
        color_item.connect("activate", self.change_color)
        menu.append(color_item)
        # New note
        new_item = Gtk.MenuItem(label="New Note")
        new_item.connect("activate", lambda x: create_new_note())
        menu.append(new_item)
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        # Delete note
        delete_item = Gtk.MenuItem(label="Delete This Note")
        delete_item.connect("activate", self.confirm_delete)
        menu.append(delete_item)
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        # Close
        close_item = Gtk.MenuItem(label="Close")
        close_item.connect("activate", self.on_close_menu)
        menu.append(close_item)
        menu.show_all()
        # Content area - notebook for switching between preview and edit
        self.notebook = Gtk.Notebook()
        self.notebook.set_show_tabs(False)
        self.add(self.notebook)
        # Preview page
        preview_scroll = Gtk.ScrolledWindow()
        preview_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.preview_view = Gtk.TextView()
        self.preview_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.preview_view.set_editable(False)
        self.preview_view.set_cursor_visible(False)
        self.preview_view.set_border_width(10)
        self.preview_buffer = self.preview_view.get_buffer()
        preview_scroll.add(self.preview_view)
        self.notebook.append_page(preview_scroll, Gtk.Label(label="Preview"))
        # Edit page
        edit_scroll = Gtk.ScrolledWindow()
        edit_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.text_view = Gtk.TextView()
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.text_view.set_border_width(10)
        self.text_buffer = self.text_view.get_buffer()
        edit_scroll.add(self.text_view)
        self.notebook.append_page(edit_scroll, Gtk.Label(label="Edit"))
        # Start in preview mode
        self.notebook.set_current_page(0)
        # Configure tags for formatting
        self.setup_text_tags()
    
    def on_close_menu(self, widget):
        """Handle close menu item click"""
        self.destroy()
    
    def on_key_press(self, widget, event):
        """Handle keyboard shortcuts for zoom"""
        # Check for Ctrl key
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_plus or event.keyval == Gdk.KEY_equal:
                self.zoom_in(None)
                return True
            elif event.keyval == Gdk.KEY_minus:
                self.zoom_out(None)
                return True
            elif event.keyval == Gdk.KEY_0:
                self.reset_zoom(None)
                return True
        return False
    
    def zoom_in(self, button):
        """Increase zoom level"""
        if self.zoom_level < 3.0:  # Max 300%
            self.zoom_level += 0.1
            self.apply_zoom()
            self.save_zoom_level()
    
    def zoom_out(self, button):
        """Decrease zoom level"""
        if self.zoom_level > 0.5:  # Min 50%
            self.zoom_level -= 0.1
            self.apply_zoom()
            self.save_zoom_level()
    
    def reset_zoom(self, button):
        """Reset zoom to 100%"""
        self.zoom_level = 1.0
        self.apply_zoom()
        self.save_zoom_level()
    
    def apply_zoom(self):
        """Apply current zoom level to text views"""
        # Update zoom label
        self.zoom_label.set_text(f"{int(self.zoom_level * 100)}%")
        # Create CSS for font size and background color
        # Get current background color
        color_path = self.get_color_path()
        bg_color = DEFAULT_COLORS[0]
        if os.path.exists(color_path):
            try:
                with open(color_path, 'r') as f:
                    bg_color = f.read().strip()
            except:
                pass
        css = f"""
        textview {{
            font-size: {12 * self.zoom_level}pt;
            background-color: {bg_color};
        }}
        textview text {{
            background-color: {bg_color};
        }}
        """.encode('utf-8')
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)
        # Apply to both text views
        Gtk.StyleContext.add_provider(
            self.text_view.get_style_context(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
        Gtk.StyleContext.add_provider(
            self.preview_view.get_style_context(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1
        )
    
    def setup_text_tags(self):
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
        self.header_tag.set_property("scale", 1.2)
        tag_table.add(self.header_tag)
        # Monospace tag for tables
        self.monospace_tag = Gtk.TextTag(name="monospace")
        self.monospace_tag.set_property("family", "monospace")
        tag_table.add(self.monospace_tag)
    
    def get_note_path(self):
        return os.path.join(data_dir, self.note_id, "text.md")
    
    def get_color_path(self):
        return os.path.join(data_dir, self.note_id, "color.txt")
    
    def get_zoom_path(self):
        return os.path.join(data_dir, self.note_id, "zoom.txt")
    
    def save_zoom_level(self):
        """Save zoom level to file"""
        zoom_path = self.get_zoom_path()
        try:
            with open(zoom_path, 'w') as f:
                f.write(str(self.zoom_level))
        except:
            pass
    
    def load_zoom_level(self):
        """Load zoom level from file"""
        zoom_path = self.get_zoom_path()
        if os.path.exists(zoom_path):
            try:
                with open(zoom_path, 'r') as f:
                    self.zoom_level = float(f.read().strip())
                # Ensure zoom level is within bounds
                self.zoom_level = max(0.5, min(3.0, self.zoom_level))
            except:
                self.zoom_level = 1.0
        else:
            self.zoom_level = 1.0
        self.apply_zoom()
    
    def load_content(self):
        note_path = self.get_note_path()
        color_path = self.get_color_path()
        # Load color
        color = DEFAULT_COLORS[0]
        if os.path.exists(color_path):
            try:
                with open(color_path, 'r') as f:
                    color = f.read().strip()
            except:
                pass
        # Apply color using CSS (will be combined with zoom in apply_zoom)
        self.apply_color_css(color)
        # Load content
        if os.path.exists(note_path):
            try:
                with open(note_path, 'r') as f:
                    content = f.read()
                self.text_buffer.set_text(content)
                self.update_preview()
                # Set window title from first line
                lines = content.splitlines()
                title = lines[0] if lines and lines[0].strip() else "Untitled"
                self.set_title(title)
            except:
                self.text_buffer.set_text("Error loading note")
                self.set_title("Error")
    
    def apply_color_css(self, color):
        # This will be overridden by apply_zoom which combines color and font size
        pass
    
    def update_preview(self):
        # Get text from editor
        start_iter = self.text_buffer.get_start_iter()
        end_iter = self.text_buffer.get_end_iter()
        text = self.text_buffer.get_text(start_iter, end_iter, True)
        # Clear preview
        self.preview_buffer.set_text("")
        # Skip first two lines (title + empty line)
        lines = text.split('\n')
        preview_lines = lines[2:] if len(lines) > 2 else []
        # Enhanced markdown parsing with table support
        i = 0
        while i < len(preview_lines):
            line = preview_lines[i]
            # Check for table
            if TableParser.is_table_line(line):
                # Collect all table lines
                table_lines = [line]
                j = i + 1
                while j < len(preview_lines) and TableParser.is_table_line(preview_lines[j]):
                    table_lines.append(preview_lines[j])
                    j += 1
                # Format and insert table
                if len(table_lines) >= 2:  # At least header + one row
                    formatted_table = TableParser.format_table(table_lines)
                    if formatted_table:
                        start = self.preview_buffer.get_end_iter()
                        self.preview_buffer.insert_with_tags(start, formatted_table + "\n\n", 
                                                             self.monospace_tag)
                i = j
                continue
            # Regular markdown parsing
            start = self.preview_buffer.get_end_iter()
            # Headers
            if line.startswith("# "):
                self.preview_buffer.insert_with_tags(start, line[2:] + "\n", self.header_tag)
            elif line.startswith("## "):
                self.preview_buffer.insert_with_tags(start, line[3:] + "\n", self.header_tag)
            # Bold and italic (simple parsing)
            elif "**" in line or "*" in line:
                self.parse_inline_formatting(line)
            else:
                self.preview_buffer.insert(start, line + "\n")
            i += 1
    
    def parse_inline_formatting(self, line):
        # Simple bold/italic parsing
        pos = 0
        start = self.preview_buffer.get_end_iter()
        while pos < len(line):
            if line.startswith("**", pos):
                end_pos = line.find("**", pos+2)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+2:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.bold_tag, len(line[pos+2:end_pos]))
                    pos = end_pos + 2
                    continue
            if line.startswith("*", pos) and not line.startswith("**", pos):
                end_pos = line.find("*", pos+1)
                if end_pos != -1:
                    self.preview_buffer.insert(start, line[pos+1:end_pos])
                    start = self.preview_buffer.get_end_iter()
                    self.apply_tag_to_last(self.italic_tag, len(line[pos+1:end_pos]))
                    pos = end_pos + 1
                    continue
            self.preview_buffer.insert(start, line[pos])
            start = self.preview_buffer.get_end_iter()
            pos += 1
        self.preview_buffer.insert(start, "\n")
    
    def apply_tag_to_last(self, tag, length):
        end_iter = self.preview_buffer.get_end_iter()
        start_iter = end_iter.copy()
        start_iter.backward_chars(length)
        self.preview_buffer.apply_tag(tag, start_iter, end_iter)
    
    def toggle_edit_mode(self, widget):
        self.is_edit_mode = not self.is_edit_mode
        if self.is_edit_mode:
            self.notebook.set_current_page(1)  # Edit
            self.text_view.grab_focus()
        else:
            self.notebook.set_current_page(0)  # Preview
        self.update_edit_button()
        # Refresh manager when toggling modes
        refresh_manager()
    
    def update_edit_button(self):
        if self.is_edit_mode:
            self.edit_item.set_label("Preview")
        else:
            self.edit_item.set_label("Edit")
    
    def on_text_changed(self, buffer):
        # Update window title from first line
        start_iter = buffer.get_start_iter()
        end_iter = start_iter.copy()
        if not end_iter.ends_line():
            end_iter.forward_to_line_end()
        first_line = buffer.get_text(start_iter, end_iter, False)
        title = first_line or "Untitled"
        self.set_title(title)
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
        try:
            with open(note_path, 'w') as f:
                f.write(text)
        except:
            pass
        self.timeout_id = None
        # Refresh manager after saving (content might have changed)
        refresh_manager()
        return False
    
    def on_close(self, window, event):
        self.save_content()
        self.save_zoom_level()
        return False  # Allow destruction
    
    def confirm_delete(self, widget):
        # Get note title for confirmation
        title = self.get_title() or "Untitled"
        # Updated MessageDialog constructor to avoid deprecation warnings
        dialog = Gtk.MessageDialog(
            parent=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete note '{title}'?"
        )
        dialog.format_secondary_text("This action cannot be undone.")
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.YES:
            self.destroy()  # Close the window first
            delete_note(self.note_id)
    
    def change_color(self, widget):
        dialog = Gtk.ColorChooserDialog(title="Choose Note Color", parent=self)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            color = dialog.get_rgba()
            hex_color = self.rgba_to_hex(color)
            # Save color
            color_path = self.get_color_path()
            try:
                with open(color_path, 'w') as f:
                    f.write(hex_color)
            except:
                pass
            # Apply new color (this will combine with current zoom)
            self.apply_zoom()
            # Refresh manager when color changes
            refresh_manager()
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
            # Restore position and size
            note.move(entry.get("x", 100), entry.get("y", 100))
            if "width" in entry and "height" in entry:
                note.resize(entry["width"], entry["height"])
            # Restore edit mode
            if entry.get("is_edit_mode", False):
                note.is_edit_mode = True
                note.notebook.set_current_page(1)
                note.update_edit_button()
            # Restore zoom level
            if "zoom_level" in entry:
                note.zoom_level = max(0.5, min(3.0, entry["zoom_level"]))
                note.apply_zoom()
            note.show_all()
            notes.append(note)
    return notes

if __name__ == "__main__":
    # Create system tray if available
    create_system_tray()
    # Try to open notes from last session
    session_notes = open_session_notes()
    if not session_notes:
        # No session found - check if we have any notes at all
        note_folders = glob.glob(os.path.join(data_dir, "note*"))
        if note_folders:
            # Open the latest note
            note_folders.sort(key=lambda x: os.path.getmtime(x), reverse=True)
            note_id = os.path.basename(note_folders[0])
            note = StickyNote(note_id)
            note.show_all()
        else:
            # No notes exist - show manager to let user create first note
            show_manager()
    Gtk.main()