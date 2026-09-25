"""Google Sheets REST client implementing ``storage.gateway.SheetsGateway``."""
from __future__ import annotations

from urllib.parse import quote

BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsClient:
    def __init__(self, rest, spreadsheet_id: str):
        self.rest = rest
        self.spreadsheet_id = spreadsheet_id

    def metadata(self) -> dict[str, int]:
        response = self.rest.request("GET", f"{BASE}/{self.spreadsheet_id}",
                                     params={"fields": "sheets.properties(sheetId,title)"})
        return {s["properties"]["title"]: s["properties"]["sheetId"] for s in response.json().get("sheets", [])}

    def get_values(self, ranges: list[str]) -> list[list[list[str]]]:
        results = []
        for start in range(0, len(ranges), 100):
            chunk = ranges[start:start + 100]
            response = self.rest.request(
                "GET", f"{BASE}/{self.spreadsheet_id}/values:batchGet",
                params=[("ranges", r) for r in chunk] + [("majorDimension", "ROWS"),
                                                        ("valueRenderOption", "FORMATTED_VALUE")])
            for value_range in response.json().get("valueRanges", []):
                results.append([[str(cell) for cell in row] for row in value_range.get("values", [])])
        return results

    def batch_update(self, requests: list[dict]) -> None:
        # One call is atomic: Google applies every request or none of them.
        self.rest.request("POST", f"{BASE}/{quote(self.spreadsheet_id)}:batchUpdate",
                          json={"requests": requests}, idempotent=False)
