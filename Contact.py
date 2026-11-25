"""
# Contact.py
# Data model representing a CRM customer contact record.
# Author: Aidana
"""

from Log import *


class Contact:
    """
    Represents a single CRM contact belonging to a Client.

    Parameters:
    ----------
    contact_id : str
        Unique contact identifier preserved as a string.
    name : str
        Full name of the contact.
    title : str, optional
        Job title of the contact (default: "").
    email : str, optional
        Email address of the contact (default: "").
    phone : str, optional
        Phone number of the contact (default: "").

    Examples:
    ---------
    1. contact = Contact("CT-1", "Jordan Lee", "Director", "jlee", "555-0100")
    2. contact = Contact.from_dict({"contact_id": "CT-1", "name": "Jordan Lee"})
    """

    def __init__(self, contact_id, name, title="", email="", phone=""):
        self._contact_id = "" if contact_id is None else str(contact_id).strip()
        self._name = "" if name is None else str(name).strip()
        self._title = "" if title is None else str(title).strip()
        self._email = "" if email is None else str(email).strip()
        self._phone = "" if phone is None else str(phone).strip()

    @property
    def contact_id(self):
        """Return the contact identifier as a string."""
        return self._contact_id

    @property
    def name(self):
        """Return the contact name."""
        return self._name

    @property
    def title(self):
        """Return the contact title."""
        return self._title

    @property
    def email(self):
        """Return the contact email."""
        return self._email

    @property
    def phone(self):
        """Return the contact phone number."""
        return self._phone

    @classmethod
    def from_dict(cls, data):
        """
        Convert a JSON dictionary record into a Contact instance.

        Parameters:
        ----------
        data : dict
            Dictionary returned by the CRM contacts endpoint.

        Examples:
        ---------
        1. contact = Contact.from_dict({"contact_id": "C-10", "name": "Alex Rivera"})
        """
        if not isinstance(data, dict):
            raise ValueError("Contact record must be a dictionary.")

        raw_id = (
            data.get("contact_id")
            if data.get("contact_id") is not None
            else data.get("id", data.get("contactId", ""))
        )

        raw_name = data.get("name")
        if raw_name is None:
            first = str(data.get("first_name", "") or "").strip()
            last = str(data.get("last_name", "") or "").strip()
            combined = (first + " " + last).strip()
            raw_name = combined if combined else data.get("contact_name", "")

        raw_title = data.get("title", data.get("job_title", data.get("role", "")))
        raw_email = data.get("email", data.get("email_address", ""))
        raw_phone = data.get("phone", data.get("phone_number", ""))

        return cls(
            contact_id=raw_id,
            name=raw_name,
            title=raw_title,
            email=raw_email,
            phone=raw_phone,
        )

    def format_summary(self):
        """
        Format actual contact fields into a readable single-line summary.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. Log.i(contact.format_summary())
        """
        return (
            f"ID={self._contact_id} | Name={self._name} | "
            f"Title={self._title} | Email={self._email} | Phone={self._phone}"
        )

    def __str__(self):
        return self.format_summary()


if __name__ == "__main__":
    sample = {
        "contact_id": "CNT-A42",
        "name": "Alex Rivera",
        "title": "VP Operations",
        "email": "arivera",
        "phone": "555-0142",
    }
    contact = Contact.from_dict(sample)
    assert contact.contact_id == "CNT-A42"
    assert contact.name == "Alex Rivera"
    assert contact.title == "VP Operations"
    Log.i(f"Contact verified: {contact.format_summary()}")
    Log.i("Testing complete - Contact checks passed")