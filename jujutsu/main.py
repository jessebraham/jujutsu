#!/usr/bin/env python

import itertools
import os
import sys
from pathlib import Path
from tkinter import *

import keyboard
import pyautogui
import pytesseract
from PIL import Image
from pystray import Icon, Menu, MenuItem

# ----------------------------------------------------------------------------
# Tesseract-OCR Configuration

# Determine the installation location of the Tesseract-OCR executable for each
# supported operating system. If the host operating system is not listed below
# then the $TESSERACT_BIN_PATH environment variable *MUST* be set.
# FIXME: add support for platforms 'darwin', 'linux'/'linux2'
if sys.platform == "win32":
    TESSERACT_BIN_PATH = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
elif os.environ.get("TESSERACT_BIN_PATH") is None:
    raise RuntimeError(
        "Tesseract binary path detection not available for your operating "
        "system, please set $TESSERACT_BIN_PATH and try again."
    )

# Specify the path to the Tesseract-OCR executable, overriding the default
# installation path with $TESSERACT_BIN_PATH if it has been set.
pytesseract.pytesseract.tesseract_cmd = os.environ.get(
    "TESSERACT_BIN_PATH", TESSERACT_BIN_PATH
)

# Use more optimal configuration specifically for Chinese/Japanese languages.
#
# OCR Engine Mode:           1  Neural nets LSTM engine only.
# Page Segmentation Mode:    6  Assume a single uniform block of text.
#
# This PSM was chosen to support both horizontal and vertical Japanese text.
# The remaining configuration comes from the Tesseract-OCR documentation.
TESSERACT_CONFIG = " ".join(
    itertools.chain(
        ("--oem", "1"),
        ("--psm", "6"),
        ("-c", "chop_enable=T"),
        ("-c", "use_new_state_cost=F"),
        ("-c", "segment_segcost_rating=F"),
        ("-c", "enable_new_segsearch=0"),
        ("-c", "language_model_ngram_on=0"),
        ("-c", "textord_force_make_prop_words=F"),
        ("-c", "edges_max_children_per_outline=40"),
    )
)

# ----------------------------------------------------------------------------
# Screen Canvas Class


class ScreenCanvas:
    def __init__(self):
        self.x = 0
        self.y = 0

        self.start_x = None
        self.start_y = None

        self.cur_x = None
        self.cur_y = None

        self.rect = None

        # Create the root window, but immediately hide it.
        self.root = Tk()
        self.root.withdraw()

        # ???
        self._init_top_level()
        self._init_screen_canvas()

    def capture(self):
        self.root.mainloop()

    def abort_capture(self):
        self._lower_screen_canvas()
        self.root.quit()

    def _init_top_level(self):
        self.top_level = Toplevel(self.root)
        self.top_level.attributes("-alpha", 0.3)
        self.top_level.attributes("-fullscreen", True)
        self.top_level.attributes("-topmost", True)
        self.top_level.attributes("-transparent", "blue")
        self.top_level.lift()

    def _init_screen_canvas(self):
        picture_frame = Frame(self.top_level, background="blue")
        picture_frame.pack(fill=BOTH, expand=YES)

        self.screen_canvas = Canvas(picture_frame, cursor="cross", bg="grey11")
        self.screen_canvas.pack(fill=BOTH, expand=YES)
        self.screen_canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.screen_canvas.bind("<B1-Motion>", self._on_mouse_move)
        self.screen_canvas.bind("<ButtonRelease-1>", self._on_mouse_up)

    def _lower_screen_canvas(self):
        if self.screen_canvas is not None:
            self.screen_canvas.destroy()
            self.screen_canvas = None

        self.top_level.attributes("-fullscreen", False)
        self.top_level.attributes("-topmost", False)
        self.top_level.withdraw()

    def _take_bounded_screenshot(self, x0, y0, x1, y1):
        self._lower_screen_canvas()

        im = pyautogui.screenshot(region=(x0, y0, x1, y1))
        result = pytesseract.image_to_string(
            im, lang="jpn+jpn_vert", config=TESSERACT_CONFIG
        )

        # FIXME: open a small window displaying the text in an editable field
        print(result)

        self.root.clipboard_clear()
        self.root.clipboard_append(result)
        self.root.update()

        self.abort_capture()

    def _on_mouse_down(self, event):
        # Save the mouse drag start position.
        self.start_x = self.screen_canvas.canvasx(event.x)
        self.start_y = self.screen_canvas.canvasy(event.y)

        # Create the selection rectangle.
        self.rect = self.screen_canvas.create_rectangle(
            self.x, self.y, 1, 1, outline="red", width=3, fill="blue"
        )

    def _on_mouse_move(self, event):
        # Update the current mouse position.
        self.cur_x = event.x
        self.cur_y = event.y

        # Expand the rectangle as you drag the mouse.
        self.screen_canvas.coords(
            self.rect, self.start_x, self.start_y, self.cur_x, self.cur_y
        )

    def _on_mouse_up(self, event):
        if self.start_x <= self.cur_x and self.start_y <= self.cur_y:
            # Moving the cursor to the right and down.
            self._take_bounded_screenshot(
                self.start_x,
                self.start_y,
                self.cur_x - self.start_x,
                self.cur_y - self.start_y,
            )
        elif self.start_x >= self.cur_x and self.start_y <= self.cur_y:
            # Moving the cursor to the left and down.
            self._take_bounded_screenshot(
                self.cur_x,
                self.start_y,
                self.start_x - self.cur_x,
                self.cur_y - self.start_y,
            )
        elif self.start_x <= self.cur_x and self.start_y >= self.cur_y:
            # Moving the cursor to the right and up.
            self._take_bounded_screenshot(
                self.start_x,
                self.cur_y,
                self.cur_x - self.start_x,
                self.start_y - self.cur_y,
            )
        elif self.start_x >= self.cur_x and self.start_y >= self.cur_y:
            # Moving the cursor to the left and up.
            self._take_bounded_screenshot(
                self.cur_x,
                self.cur_y,
                self.start_x - self.cur_x,
                self.start_y - self.cur_y,
            )

        return event


# ----------------------------------------------------------------------------
# Application


class TrayApplication:
    def __init__(self):
        icon_path = Path("resources/icon.ico").absolute()
        self.icon = Icon(
            "呪術 (jujutsu)",
            Image.open(icon_path),
            menu=Menu(
                MenuItem("Capture (ctrl+`)", self._capture_action),
                MenuItem("Quit", self._exit_action),
            ),
        )

        self.screen_canvas = None

        keyboard.add_hotkey("ctrl+`", self._capture_action)
        keyboard.add_hotkey("esc", self._abort_action)

    def run(self):
        self.icon.run()

    def _capture_action(self):
        if self.screen_canvas is not None:
            return

        self.screen_canvas = ScreenCanvas()
        self.screen_canvas.capture()
        self.screen_canvas = None

    def _abort_action(self):
        if self.screen_canvas is None:
            return

        self.screen_canvas.abort_capture()
        self.screen_canvas = None

    def _exit_action(self):
        self._abort_action()
        self.icon.visible = False
        self.icon.stop()


def main():
    app = TrayApplication()
    app.run()


if __name__ == "__main__":
    main()
