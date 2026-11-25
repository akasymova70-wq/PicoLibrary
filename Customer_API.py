"""
# Customer_API.py
# Local MicroPython REST wrapper that constructs CRM endpoint URLs and delegates JSON
# requests to an injected PicoLibrary Net instance.
# Author: Aidana
"""

from Log import *


class Customer_API:
    """
    Local MicroPython wrapper for the CRM REST API.

    Constructs endpoint URLs internally and calls net.getJson(url).
    Does not expose get_all_activities() because Sequence B loads details per customer.

    Parameters:
    ----------
    net : Net
        Injected PicoLibrary Net instance used to execute HTTP GET JSON requests.
    base_url : str, optional
        Optional base REST URL prepended to relative endpoint paths (default: "").
    version_url : str, optional
        Endpoint URL or relative path for the API version check (default: "").
    customers_url : str, optional
        Endpoint URL or relative path for retrieving all customers (default: "").
    contacts_url : str, optional
        Endpoint URL or relative path for retrieving a customer's contacts (default: "").
    activities_url : str, optional
        Endpoint URL or relative path for retrieving a customer's activities (default: "").

    Examples:
    ---------
    1. api = Customer_API(net, base_url=..., version_url=..., customers_url=..., contacts_url=..., activities_url=...)
    2. version = api.get_version()
    3. customers = api.get_customers()
    """

    def __init__(
        self,
        net,
        base_url="",
        version_url="",
        customers_url="",
        contacts_url="",
        activities_url="",
    ):
        if net is None:
            raise ValueError("Customer_API requires a valid Net instance.")
        self._net = net
        self._base_url = (base_url or "").strip()
        self._version_url = (version_url or "").strip()
        self._customers_url = (customers_url or "").strip()
        self._contacts_url = (contacts_url or "").strip()
        self._activities_url = (activities_url or "").strip()

    def _build_url(self, endpoint, item_id=None, operation_name="request"):
        """Build the target request URL without logging private endpoint strings."""
        ep = (endpoint or "").strip()
        if not ep:
            raise ValueError(
                f"Missing endpoint configuration for {operation_name} in secrets.py."
            )

        if ep.startswith("http://") or ep.startswith("https://"):
            url = ep
        elif self._base_url:
            url = self._base_url.rstrip("/") + "/" + ep.lstrip("/")
        else:
            url = ep

        if item_id is not None:
            clean_id = str(item_id).strip()
            if not clean_id:
                raise ValueError(f"Invalid empty customer_id for {operation_name}.")
            if "{id}" in url:
                url = url.replace("{id}", clean_id)
            elif ":cust_id" in url:
                url = url.replace(":cust_id", clean_id)
            elif ":id" in url:
                url = url.replace(":id", clean_id)
            else:
                url = url.rstrip("/") + "/" + clean_id

        return url

    def _fetch_json(self, url, operation_name, customer_id=None):
        """Execute Net.getJson(url) and validate connectivity, HTTP status, and payload."""
        if not self._net.isConnected():
            raise RuntimeError(
                f"Cannot execute {operation_name}: Wi-Fi is not connected."
            )

        if customer_id is not None:
            Log.i(
                f"Customer_API: executing {operation_name} for customer_id={customer_id}"
            )
        else:
            Log.i(f"Customer_API: executing {operation_name}")

        payload = self._net.getJson(url)
        status_code = getattr(self._net, "status_code", None)

        if payload is None:
            if status_code is not None and status_code >= 400:
                raise RuntimeError(
                    f"{operation_name} failed with HTTP status {status_code}."
                )
            raise RuntimeError(
                f"{operation_name} returned no valid JSON (network, HTTP, or JSON error)."
            )

        if status_code is not None and status_code >= 400:
            raise RuntimeError(
                f"{operation_name} failed with HTTP status {status_code}."
            )

        return payload

    def _extract_list(self, payload, candidate_keys, operation_name):
        """Normalize a list response whether returned directly or wrapped in an object."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in candidate_keys:
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        raise RuntimeError(
            f"{operation_name} returned unexpected JSON structure (expected list)."
        )

    def get_version(self):
        """
        Retrieve API version metadata from the version endpoint.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. version_info = api.get_version()
        """
        url = self._build_url(self._version_url, operation_name="get_version")
        return self._fetch_json(url, "get_version")

    def get_customers(self):
        """
        Retrieve the list of customer records from the customers endpoint.

        Parameters:
        ----------
        None

        Examples:
        ---------
        1. customer_records = api.get_customers()
        """
        url = self._build_url(self._customers_url, operation_name="get_customers")
        payload = self._fetch_json(url, "get_customers")
        return self._extract_list(
            payload, ("customers", "clients", "data", "items"), "get_customers"
        )

    def get_customer(self, customer_id):
        """
        Retrieve a single customer record by customer_id.

        Parameters:
        ----------
        customer_id : str
            Identifier of the customer to retrieve.

        Examples:
        ---------
        1. record = api.get_customer("CUST-1")
        """
        customer_base = self._customers_url.rstrip("/")
        if customer_base.endswith("get_customers"):
            customer_base = customer_base[:-1]
        url = self._build_url(
            customer_base, item_id=customer_id, operation_name="get_customer"
        )
        payload = self._fetch_json(url, "get_customer", customer_id=customer_id)
        if isinstance(payload, dict):
            if "customer" in payload and isinstance(payload["customer"], dict):
                return payload["customer"]
            return payload
        if isinstance(payload, list) and len(payload) > 0 and isinstance(payload[0], dict):
            return payload[0]
        raise RuntimeError("get_customer returned empty or unexpected JSON structure.")

    def get_contacts(self, customer_id):
        """
        Retrieve the contact records for one selected customer_id.

        Parameters:
        ----------
        customer_id : str
            Identifier of the selected customer.

        Examples:
        ---------
        1. contacts = api.get_contacts("CUST-1")
        """
        url = self._build_url(
            self._contacts_url, item_id=customer_id, operation_name="get_contacts"
        )
        payload = self._fetch_json(url, "get_contacts", customer_id=customer_id)
        return self._extract_list(
            payload, ("contacts", "data", "items"), "get_contacts"
        )

    def get_activities(self, customer_id):
        """
        Retrieve the activity records for one selected customer_id.

        Parameters:
        ----------
        customer_id : str
            Identifier of the selected customer.

        Examples:
        ---------
        1. activities = api.get_activities("CUST-1")
        """
        url = self._build_url(
            self._activities_url, item_id=customer_id, operation_name="get_activities"
        )
        payload = self._fetch_json(url, "get_activities", customer_id=customer_id)
        return self._extract_list(
            payload, ("activities", "data", "items"), "get_activities"
        )


if __name__ == "__main__":
    class _MockNet:
        def __init__(self):
            self.status_code = 200
            self.calls = []

        def isConnected(self):
            return True

        def getJson(self, url):
            self.calls.append(url)
            if url == "route_version":
                return {"version": "1.0"}
            if url == "route_customers":
                return [{"customer_id": "C-1", "name": "Demo Co"}]
            if url == "route_contacts/C-1":
                return [{"contact_id": "CT-1", "name": "Taylor"}]
            if url == "route_activities/C-1":
                return [{"activity_id": "AC-1", "type": "Call"}]
            return None

    mock_net = _MockNet()
    api = Customer_API(
        mock_net,
        version_url="route_version",
        customers_url="route_customers",
        contacts_url="route_contacts",
        activities_url="route_activities",
    )
    assert api.get_version()["version"] == "1.0"
    assert len(api.get_customers()) == 1
    assert len(api.get_contacts("C-1")) == 1
    assert len(api.get_activities("C-1")) == 1
    assert not hasattr(api, "get_all_activities")
    Log.i("Testing complete - Customer_API checks passed")