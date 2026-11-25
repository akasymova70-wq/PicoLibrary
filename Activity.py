"""
# Activity.py
# Data model representing a CRM customer activity record.
# Author: Aidana
"""

from Log import *


class Activity:
    """
    Represents a single CRM activity belonging to a Client.

    Parameters:
    ----------
    activity_id : str
        Unique activity identifier preserved safely as a string.
    activity_type : str, optional
        Category or type of activity (default: "").
    activity_name : str, optional
        Short title or subject of the activity (default: "").
    activity_date : str, optional
        Date string associated with the activity (default: "").
    owner : str, optional
        Owner or assignee for the activity (default: "").
    location : str, optional
        Location or channel for the activity (default: "").

    Examples:
    ---------
    1. act = Activity("ACT-9", "Call", "Renewal Review", "2026-11-15", "Morgan", "Phone")
    2. act = Activity.from_dict({"activity_id": "ACT-9", "type": "Call"})
    """

    def __init__(
        self,
        activity_id,
        activity_type="",
        activity_name="",
        activity_date="",
        owner="",
        location="",
    ):
        self._activity_id = "" if activity_id is None else str(activity_id).strip()
        self._type = "" if activity_type is None else str(activity_type).strip()
        self._activity_name = (
            "" if activity_name is None else str(activity_name).strip()
        )
        self._activity_date = (
            "" if activity_date is None else str(activity_date).strip()
        )
        self._owner = "" if owner is None else str(owner).strip()
        self._location = "" if location is None else str(location).strip()

    @property
    def activity_id(self):
        """Return the activity identifier as a string."""
        return self._activity_id

    @property
    def type(self):
        """Return the activity type."""
        return self._type

    @property
    def activity_name(self):
        """Return the activity name."""
        return self._activity_name

    @property
    def activity_date(self):
        """Return the activity date."""
        return self._activity_date

    @property
    def owner(self):
        """Return the activity owner."""
        return self._owner

    @property
    def location(self):
        """Return the activity location."""
        return self._location

    @classmethod
    def from_dict(cls, data):
        """
        Convert a JSON dictionary record into an Activity instance.

        Parameters:
        ----------
        data : dict
            Dictionary returned by the CRM activities endpoint.

        Examples:
        ---------
        1. act = Activity.from_dict({"activity_id": "ACT-1", "type": "Meeting"})
        """
        if not isinstance(data, dict):
            raise ValueError("Activity record must be a dictionary.")

        raw_id = (
            data.get("activity_id")
            if data.get("activity_id") is not None
            else data.get("id", data.get("activityId", ""))
        )
        raw_type = data.get("type", data.get("activity_type", ""))
        raw_name = data.get(
            "activity_name", data.get("name", data.get("subject", data.get("title", "")))
        )
        raw_date = data.get("activity_date", data.get("date", ""))
        raw_owner = data.get("owner", data.get("assigned_to", ""))
        raw_location = data.get("location", "")

        return cls(
            activity_id=raw_id,
            activity_type=raw_type,
            activity_name=raw_name,
            activity_date=raw_date,
            owner=raw_owner,
            location=raw_location,
        )

    def format_summary(self):
        """
        Format actual activity fields into a readable single-line summary.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. Log.i(activity.format_summary())
        """
        return (
            f"ID={self._activity_id} | Type={self._type} | Name={self._activity_name} | "
            f"Date={self._activity_date} | Owner={self._owner} | Location={self._location}"
        )

    def __str__(self):
        return self.format_summary()


if __name__ == "__main__":
    sample = {
        "activity_id": "ACT-Z9",
        "type": "Meeting",
        "activity_name": "Q4 Review",
        "activity_date": "2026-11-18",
        "owner": "Morgan",
        "location": "Room B",
    }
    activity = Activity.from_dict(sample)
    assert activity.activity_id == "ACT-Z9"
    assert activity.type == "Meeting"
    assert activity.activity_name == "Q4 Review"
    Log.i(f"Activity verified: {activity.format_summary()}")
    Log.i("Testing complete - Activity checks passed")