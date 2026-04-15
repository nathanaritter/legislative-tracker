"""
Fallback AG Grid table listing bills matching current filters.
"""

from dash import html
import dash_ag_grid as dag


COLUMN_DEFS = [
    {"field": "state", "headerName": "State", "width": 80, "pinned": "left"},
    {"field": "bill_number", "headerName": "Bill #", "width": 110, "pinned": "left"},
    {"field": "title", "headerName": "Title", "flex": 2, "wrapText": True, "autoHeight": True,
     "cellStyle": {"whiteSpace": "normal", "lineHeight": "1.3"}},
    {"field": "current_status", "headerName": "Status", "width": 130},
    {"field": "ai_risk_score", "headerName": "Risk", "width": 90,
     "valueFormatter": {"function": "params.value == null ? '' : params.value.toFixed(0)"}},
    {"field": "introduced_date", "headerName": "Introduced", "width": 120},
    {"field": "last_action_date", "headerName": "Last action", "width": 120},
    {"field": "jurisdiction_name", "headerName": "Jurisdiction", "width": 170},
]


def build_bill_grid_card():
    return html.Div(
        [
            html.H5("Bills"),
            dag.AgGrid(
                id="bill-grid",
                columnDefs=COLUMN_DEFS,
                rowData=[],
                defaultColDef={"sortable": True, "filter": True, "resizable": True},
                className="ag-theme-alpine",
                style={"height": "420px"},
                dashGridOptions={"rowSelection": "single"},
            ),
        ],
        className="card",
    )
