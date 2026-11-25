"""
# Client.py
# Data model representing a CRM customer/client aggregating Contact and Activity records.
# Author: Aidana
"""

from Log import *


def _safe_float(value, default=0.0):
    """Safely convert numeric financial fields to float without crashing."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class Client:
    """
    Represents a CRM customer record and aggregates zero or more Contact and Activity objects.

    Parameters:
    ----------
    customer_id : str
        Unique customer identifier preserved safely as a string.
    name : str
        Customer or company name.
    discount_level : float, optional
        Customer discount level (default: 0.0).
    total_contract_value : float, optional
        Total contract value (default: 0.0).
    annual_recurring_revenue : float, optional
        Annual recurring revenue (default: 0.0).

    Examples:
    ---------
    1. client = Client("CUST-101", "Northwind", 10.0, 50000.0, 12000.0)
    2. client.set_contacts([contact])
    3. client.set_activities([activity])
    """

    def __init__(
        self,
        customer_id,
        name,
        discount_level=0.0,
        total_contract_value=0.0,
        annual_recurring_revenue=0.0,
    ):
        self._customer_id = "" if customer_id is None else str(customer_id).strip()
        self._name = "" if name is None else str(name).strip()
        self._discount_level = _safe_float(discount_level)
        self._total_contract_value = _safe_float(total_contract_value)
        self._annual_recurring_revenue = _safe_float(annual_recurring_revenue)
        self._contacts = []
        self._activities = []
        self._contacts_loaded = False
        self._activities_loaded = False

    @property
    def customer_id(self):
        """Return the customer identifier as a string."""
        return self._customer_id

    @property
    def name(self):
        """Return the customer name."""
        return self._name

    @property
    def discount_level(self):
        """Return the discount level."""
        return self._discount_level

    @property
    def total_contract_value(self):
        """Return the total contract value."""
        return self._total_contract_value

    @property
    def annual_recurring_revenue(self):
        """Return the annual recurring revenue."""
        return self._annual_recurring_revenue

    @property
    def contacts(self):
        """Return a shallow copy of stored Contact objects."""
        return list(self._contacts)

    @property
    def activities(self):
        """Return a shallow copy of stored Activity objects."""
        return list(self._activities)

    @property
    def details_loaded(self):
        """Return True once both contacts and activities have been stored."""
        return self._contacts_loaded and self._activities_loaded

    def set_contacts(self, contacts):
        """
        Store loaded Contact objects on this Client.

        Parameters:
        ----------
        contacts : list
            List of Contact instances belonging to this Client.

        Examples:
        ---------
        1. client.set_contacts(contact_list)
        """
        if contacts is None or not isinstance(contacts, list):
            raise TypeError("contacts must be a list of Contact objects.")
        self._contacts = list(contacts)
        self._contacts_loaded = True

    def set_activities(self, activities):
        """
        Store loaded Activity objects on this Client.

        Parameters:
        ----------
        activities : list
            List of Activity instances belonging to this Client.

        Examples:
        ---------
        1. client.set_activities(activity_list)
        """
        if activities is None or not isinstance(activities, list):
            raise TypeError("activities must be a list of Activity objects.")
        self._activities = list(activities)
        self._activities_loaded = True

    @classmethod
    def from_dict(cls, data):
        """
        Convert a JSON dictionary record into a Client instance.

        Parameters:
        ----------
        data : dict
            Dictionary returned by the CRM customers endpoint.

        Examples:
        ---------
        1. client = Client.from_dict({"customer_id": "CUST-01", "name": "Acme"})
        """
        if not isinstance(data, dict):
            raise ValueError("Client record must be a dictionary.")

        raw_id = (
            data.get("customer_id")
            if data.get("customer_id") is not None
            else data.get("id", data.get("cust_id", data.get("customerId", "")))
        )
        raw_name = data.get("name", data.get("customer_name", data.get("company", "")))
        raw_discount = data.get("discount_level", data.get("discount", 0.0))
        raw_tcv = data.get("total_contract_value", data.get("tcv", 0.0))
        raw_arr = data.get("annual_recurring_revenue", data.get("arr", 0.0))

        return cls(
            customer_id=raw_id,
            name=raw_name,
            discount_level=raw_discount,
            total_contract_value=raw_tcv,
            annual_recurring_revenue=raw_arr,
        )

    def __str__(self):
        return (
            f"Client(ID={self._customer_id}, Name={self._name}, "
            f"Contacts={len(self._contacts)}, Activities={len(self._activities)})"
        )


if __name__ == "__main__":
    from Contact import Contact
    from Activity import Activity

    client = Client.from_dict(
        {
            "customer_id": "CUST-7B",
            "name": "Apex Labs",
            "discount_level": 12.5,
            "total_contract_value": 120000,
            "annual_recurring_revenue": 40000,
        }
    )
    assert client.customer_id == "CUST-7B"
    assert client.details_loaded is False

    client.set_contacts([Contact("C-1", "Sam Chen", "Lead")])
    client.set_activities([Activity("A-1", "Call", "Check-in", "2026-11-10")])
    assert client.details_loaded is True
    assert len(client.contacts) == 1
    assert len(client.activities) == 1

    Log.i(f"Client verified: {client}")
    Log.i("Testing complete - Client checks passed")