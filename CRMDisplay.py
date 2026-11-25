"""
# CRMDisplay.py
# Custom 16x2 LCD display subclass extending PicoLibrary's LCDDisplay for CRM views
# with nonblocking multi-page cycling.
# Author: Aidana
"""

import time
from Log import *

try:
    from Displays import LCDDisplay
except ImportError:
    LCDDisplay = object


def _ticks_ms():
    """Return a millisecond timestamp compatible with both MicroPython and CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(now_ms, past_ms):
    """Compute elapsed milliseconds safely across MicroPython tick wrap-around."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(now_ms, past_ms)
    return now_ms - past_ms


def _format_money(amount):
    """Compactly format numeric values to fit a 16-character LCD row."""
    try:
        val = float(amount)
    except (TypeError, ValueError):
        return "0"
    if abs(val) >= 1000000:
        return f"${val / 1000000:.1f}M"
    if abs(val) >= 1000:
        return f"${val / 1000:.1f}K"
    return f"${val:.0f}"


class CRMDisplay(LCDDisplay):
    """
    Application-specific 16x2 LCD display inheriting from PicoLibrary LCDDisplay.

    Requires explicit hardware pins (no numeric pin defaults) and supports
    nonblocking multi-page display updates driven by update() in the main loop.

    Parameters:
    ----------
    sda : int, optional
        I2C SDA GPIO pin (must be provided together with scl for I2C mode).
    scl : int, optional
        I2C SCL GPIO pin (must be provided together with sda for I2C mode).
    i2c_addr : int, optional
        Optional explicit I2C address (default: None for auto-scan).
    rs : int, optional
        Parallel RS pin (all parallel pins required if using parallel mode).
    e : int, optional
        Parallel Enable pin.
    d4 : int, optional
        Parallel D4 pin.
    d5 : int, optional
        Parallel D5 pin.
    d6 : int, optional
        Parallel D6 pin.
    d7 : int, optional
        Parallel D7 pin.
    page_interval_ms : int, optional
        Milliseconds between automatic nonblocking page advances (default: 2500).

    Examples:
    ---------
    1. display = CRMDisplay(sda=sda_pin, scl=scl_pin)
    2. display.show_customer(client)
    3. display.update()
    """

    COLS = 16

    def __init__(
        self,
        *,
        sda=None,
        scl=None,
        i2c_addr=None,
        rs=None,
        e=None,
        d4=None,
        d5=None,
        d6=None,
        d7=None,
        page_interval_ms=2500,
    ):
        i2c_selected = sda is not None or scl is not None
        parallel_pins = (rs, e, d4, d5, d6, d7)
        parallel_selected = any(p is not None for p in parallel_pins)

        if i2c_selected and parallel_selected:
            raise ValueError(
                "CRMDisplay configuration error: specify either I2C pins (sda, scl) "
                "or parallel pins (rs, e, d4, d5, d6, d7), not both."
            )

        if i2c_selected:
            if sda is None or scl is None:
                raise ValueError(
                    "CRMDisplay I2C configuration incomplete: both sda and scl pins are required."
                )
            super().__init__(sda=sda, scl=scl, i2c_addr=i2c_addr)
        elif parallel_selected:
            if any(p is None for p in parallel_pins):
                raise ValueError(
                    "CRMDisplay parallel configuration incomplete: rs, e, d4, d5, d6, and d7 are all required."
                )
            super().__init__(rs=rs, e=e, d4=d4, d5=d5, d6=d6, d7=d7)
        else:
            raise ValueError(
                "CRMDisplay configuration missing: configure I2C (sda, scl) or parallel LCD pins."
            )

        self._pages = []
        self._page_index = 0
        self._page_interval_ms = max(500, int(page_interval_ms))
        self._last_page_ms = _ticks_ms()
        self._paging_active = False

    def _fit_line(self, text):
        """Normalize text to a clean 16-character string padded with spaces."""
        clean = "" if text is None else str(text).replace("\r", " ").replace("\n", " ").strip()
        if len(clean) > self.COLS:
            clean = clean[: self.COLS]
        return clean + (" " * (self.COLS - len(clean)))

    def _render_lines(self, line1, line2=""):
        """Write two padded 16-character lines directly to rows 0 and 1."""
        row0 = self._fit_line(line1)
        row1 = self._fit_line(line2)
        self.showText(row0, 0, 0)
        self.showText(row1, 1, 0)
        Log.i(f"CRMDisplay: LCD updated -> [{row0.strip()}] | [{row1.strip()}]")

    def _set_pages(self, pages):
        """Store in-memory pages and display the first page immediately."""
        self._pages = list(pages) if pages else [("", "")]
        self._page_index = 0
        self._last_page_ms = _ticks_ms()
        self._paging_active = len(self._pages) > 1
        line1, line2 = self._pages[0]
        self._render_lines(line1, line2)

    def show_customer(self, client):
        """
        Display a selected customer summary across concise 16x2 LCD pages.

        Parameters:
        ----------
        client : Client
            Selected Client object to display.

        Examples:
        ---------
        1. display.show_customer(selected_client)
        """
        if client is None:
            self.show_status("No Customer", "List is empty")
            return

        name_line = client.name or "(Unnamed)"
        id_line = client.customer_id or "(No ID)"
        tcv_str = _format_money(client.total_contract_value)
        arr_str = _format_money(client.annual_recurring_revenue)
        disc_str = f"{client.discount_level:g}%"

        pages = [
            (name_line, id_line),
            (f"TCV {tcv_str}", f"ARR {arr_str} {disc_str}"),
        ]
        self._set_pages(pages)

    def show_details(self, client, contacts, activities, view="Contacts"):
        """
        Display loaded Contacts or Activities for a client using in-memory data only.

        Parameters:
        ----------
        client : Client
            Selected Client object.
        contacts : list
            Loaded Contact objects for the client.
        activities : list
            Loaded Activity objects for the client.
        view : str, optional
            Active detail view, either "Contacts" or "Activities" (default: "Contacts").

        Examples:
        ---------
        1. display.show_details(client, client.contacts, client.activities, "Contacts")
        """
        if client is None:
            self.show_status("No Customer", "Select a client")
            return

        active_view = "Activities" if view == "Activities" else "Contacts"
        pages = []

        if active_view == "Contacts":
            if not contacts:
                pages.append((client.name or client.customer_id, "No contacts"))
            else:
                total = len(contacts)
                for idx, contact in enumerate(contacts, 1):
                    header = f"C{idx}/{total} {contact.name}".strip()
                    secondary = (
                        contact.title
                        or contact.phone
                        or contact.email
                        or contact.contact_id
                    )
                    pages.append((header, secondary))

                    detail_top = contact.email or contact.phone
                    detail_bottom = contact.phone if contact.email else contact.contact_id
                    if detail_top and (detail_top != secondary or detail_bottom):
                        pages.append((detail_top, detail_bottom))
        else:
            if not activities:
                pages.append((client.name or client.customer_id, "No activities"))
            else:
                total = len(activities)
                for idx, activity in enumerate(activities, 1):
                    title_part = activity.activity_name or activity.type or activity.activity_id
                    header = f"A{idx}/{total} {title_part}".strip()
                    meta = f"{activity.type} {activity.activity_date}".strip() or activity.activity_id
                    pages.append((header, meta))

                    if activity.owner or activity.location:
                        top = activity.owner or activity.location
                        bottom = activity.location if activity.owner else activity.activity_date
                        pages.append((top, bottom))

        self._set_pages(pages)

    def show_next_page(self):
        """
        Advance to the next in-memory LCD page with wrap-around.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. display.show_next_page()
        """
        if not self._pages:
            return
        self._page_index = (self._page_index + 1) % len(self._pages)
        line1, line2 = self._pages[self._page_index]
        self._render_lines(line1, line2)

    def update(self):
        """
        Nonblocking display update called repeatedly by the main loop to advance pages.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. display.update()
        """
        if not self._paging_active or len(self._pages) <= 1:
            return False
        now_ms = _ticks_ms()
        if _ticks_diff(now_ms, self._last_page_ms) >= self._page_interval_ms:
            self._last_page_ms = now_ms
            self.show_next_page()
            return True
        return False

    def show_status(self, line1, line2=""):
        """
        Display a static two-line status message and pause automatic paging.

        Parameters:
        ----------
        line1 : str
            Text for LCD row 0.
        line2 : str, optional
            Text for LCD row 1 (default: "").

        Examples:
        ---------
        1. display.show_status("Loading Details", "Please wait")
        """
        self._paging_active = False
        self._pages = [(line1, line2)]
        self._page_index = 0
        self._render_lines(line1, line2)

    def show_error(self, message):
        """
        Display a readable error message on the 16x2 LCD without crashing.

        Parameters:
        ----------
        message : str
            Short user-facing error description.

        Examples:
        ---------
        1. display.show_error("WiFi failed")
        """
        clean = "Unknown error" if not message else str(message).strip()
        if len(clean) <= self.COLS:
            self.show_status("Error", clean)
        else:
            self.show_status(clean[: self.COLS], clean[self.COLS : self.COLS * 2])


if __name__ == "__main__":
    from Client import Client
    from Contact import Contact
    from Activity import Activity

    class _HeadlessCRMDisplay(CRMDisplay):
        def __init__(self, page_interval_ms=500):
            self.rendered = []
            self._pages = []
            self._page_index = 0
            self._page_interval_ms = page_interval_ms
            self._last_page_ms = _ticks_ms()
            self._paging_active = False

        def showText(self, text, row=0, col=0):
            self.rendered.append((row, text))

    try:
        CRMDisplay()
        assert False, "Expected ValueError when no pins are supplied"
    except ValueError as err:
        Log.i(f"Configuration check passed: {err}")

    disp = _HeadlessCRMDisplay(page_interval_ms=500)
    client = Client("CUST-1", "Northwind Co", 5.0, 75000, 25000)
    contacts = [Contact("CT-1", "Jordan Lee", "Director", "jlee", "555-0101")]
    activities = [Activity("AC-1", "Call", "Kickoff", "2026-11-12", "Pat", "Phone")]

    disp.show_customer(client)
    disp.show_next_page()
    disp.show_details(client, contacts, activities, "Contacts")
    disp.show_details(client, contacts, activities, "Activities")
    disp.show_error("Network timeout")
    assert len(disp.rendered) >= 10
    Log.i("Testing complete - CRMDisplay checks passed")