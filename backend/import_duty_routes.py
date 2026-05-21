"""
import_duty_routes.py — Import Duty Calculator routes.
NEW FILE. Mounted in main.py.

Routes:
  GET  /import-duty              (page)
  POST /api/import-duty/calculate
"""

from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from schemas_payroll import ImportDutyRequest, ImportDutyResponse
from import_duty_service import calculate_import_duty

router = APIRouter()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


@router.get("/import-duty", response_class=HTMLResponse, include_in_schema=False)
async def page_import_duty(request: Request):
    return templates.TemplateResponse("import_duty.html", {"request": request})


@router.post(
    "/api/import-duty/calculate",
    response_model=ImportDutyResponse,
    tags=["Import Duty"],
)
async def calculate_duty(body: ImportDutyRequest):
    """
    Estimate Zimbabwe import duties and total landed cost.

    Returns duty, VAT, surtax, and total cost breakdown.
    Rates are estimates — verify with a licensed customs agent.
    """
    return calculate_import_duty(body)
