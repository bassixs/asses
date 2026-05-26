from __future__ import annotations

from html import escape
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import async_session_maker, init_db
from bot.models import AssessmentResult, InterviewRecord, NotebookFillResult, ObserverNotebook

app = FastAPI(title="HR Assessment Bot Admin", docs_url=None, redoc_url=None)
security = HTTPBasic()


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()


async def get_admin_session() -> AsyncSession:
    async with async_session_maker() as session:
        yield session


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PASSWORD is not configured",
        )

    username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> str:
    records = list(
        await session.scalars(select(InterviewRecord).order_by(desc(InterviewRecord.created_at)).limit(200))
    )
    notebooks = list(
        await session.scalars(select(ObserverNotebook).order_by(desc(ObserverNotebook.created_at)).limit(200))
    )
    assessments = list(
        await session.scalars(select(AssessmentResult).order_by(desc(AssessmentResult.created_at)).limit(200))
    )
    fills = list(
        await session.scalars(select(NotebookFillResult).order_by(desc(NotebookFillResult.created_at)).limit(200))
    )
    counts = {
        "records": await session.scalar(select(func.count(InterviewRecord.id))) or 0,
        "notebooks": await session.scalar(select(func.count(ObserverNotebook.id))) or 0,
        "assessments": await session.scalar(select(func.count(AssessmentResult.id))) or 0,
        "fills": await session.scalar(select(func.count(NotebookFillResult.id))) or 0,
    }
    message = request.query_params.get("message", "")
    return _page(
        message=message,
        counts=counts,
        records=records,
        notebooks=notebooks,
        assessments=assessments,
        fills=fills,
    )


@app.post("/delete/record/{record_id}")
async def delete_record(
    record_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> RedirectResponse:
    record = await session.get(InterviewRecord, record_id)
    if record is None:
        return _redirect("Запись не найдена")

    await _delete_record(session, record)
    await session.commit()
    return _redirect(f"Запись #{record_id} удалена")


@app.post("/delete/notebook/{notebook_id}")
async def delete_notebook(
    notebook_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> RedirectResponse:
    notebook = await session.get(ObserverNotebook, notebook_id)
    if notebook is None:
        return _redirect("Блокнот не найден")

    await _delete_notebook(session, notebook)
    await session.commit()
    return _redirect(f"Блокнот #{notebook_id} удален")


@app.post("/delete/fill/{fill_id}")
async def delete_fill(
    fill_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> RedirectResponse:
    fill = await session.get(NotebookFillResult, fill_id)
    if fill is None:
        return _redirect("Заполненный файл не найден")

    _safe_unlink(fill.output_path)
    await session.delete(fill)
    await session.commit()
    return _redirect(f"Результат заполнения #{fill_id} удален")


@app.post("/delete/assessment/{assessment_id}")
async def delete_assessment(
    assessment_id: int,
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> RedirectResponse:
    assessment = await session.get(AssessmentResult, assessment_id)
    if assessment is None:
        return _redirect("Оценка не найдена")

    await session.delete(assessment)
    await session.commit()
    return _redirect(f"Оценка #{assessment_id} удалена")


@app.post("/delete/all")
async def delete_all(
    _: str = Depends(require_admin),
    session: AsyncSession = Depends(get_admin_session),
) -> RedirectResponse:
    records = list(await session.scalars(select(InterviewRecord)))
    notebooks = list(await session.scalars(select(ObserverNotebook)))
    fills = list(await session.scalars(select(NotebookFillResult)))

    for record in records:
        _safe_unlink(record.file_path)
    for notebook in notebooks:
        _safe_unlink(notebook.file_path)
    for fill in fills:
        _safe_unlink(fill.output_path)

    await session.execute(delete(NotebookFillResult))
    await session.execute(delete(AssessmentResult))
    await session.execute(delete(ObserverNotebook))
    await session.execute(delete(InterviewRecord))
    await session.commit()
    _delete_empty_runtime_dirs()
    return _redirect("Все загруженные данные удалены")


async def _delete_record(session: AsyncSession, record: InterviewRecord) -> None:
    fills = list(await session.scalars(select(NotebookFillResult).where(NotebookFillResult.record_id == record.id)))
    for fill in fills:
        _safe_unlink(fill.output_path)
        await session.delete(fill)
    await session.execute(delete(AssessmentResult).where(AssessmentResult.record_id == record.id))
    _safe_unlink(record.file_path)
    await session.delete(record)


async def _delete_notebook(session: AsyncSession, notebook: ObserverNotebook) -> None:
    fills = list(
        await session.scalars(select(NotebookFillResult).where(NotebookFillResult.notebook_id == notebook.id))
    )
    for fill in fills:
        _safe_unlink(fill.output_path)
        await session.delete(fill)
    _safe_unlink(notebook.file_path)
    await session.delete(notebook)


def _page(
    *,
    message: str,
    counts: dict[str, int],
    records: list[InterviewRecord],
    notebooks: list[ObserverNotebook],
    assessments: list[AssessmentResult],
    fills: list[NotebookFillResult],
) -> str:
    return f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HR Assessment Bot Admin</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f6f7f9; color: #1f2937; }}
    header {{ background: #111827; color: #fff; padding: 22px 32px; }}
    main {{ padding: 24px 32px 40px; max-width: 1280px; margin: 0 auto; }}
    h1 {{ margin: 0; font-size: 24px; }}
    h2 {{ margin-top: 28px; font-size: 19px; }}
    .muted {{ color: #6b7280; }}
    .stats {{ display: grid; grid-template-columns: repeat(4, minmax(130px, 1fr)); gap: 12px; margin-top: 18px; }}
    .stat {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px; }}
    .stat strong {{ display: block; font-size: 24px; margin-top: 4px; }}
    .notice {{ background: #ecfdf5; border: 1px solid #a7f3d0; padding: 12px 14px; border-radius: 8px; margin: 16px 0; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #e5e7eb; vertical-align: top; font-size: 14px; }}
    th {{ background: #f3f4f6; font-weight: 700; }}
    tr:last-child td {{ border-bottom: none; }}
    code {{ background: #f3f4f6; padding: 2px 5px; border-radius: 4px; }}
    form {{ margin: 0; display: inline; }}
    button {{ border: 0; background: #2563eb; color: white; padding: 7px 10px; border-radius: 6px; cursor: pointer; }}
    button.danger {{ background: #dc2626; }}
    button:hover {{ opacity: .92; }}
    .top-actions {{ margin-top: 18px; }}
  </style>
</head>
<body>
  <header>
    <h1>HR Assessment Bot Admin</h1>
    <div class="muted">Просмотр и удаление загруженных файлов, транскриптов, блокнотов и отчетов</div>
  </header>
  <main>
    {f'<div class="notice">{escape(message)}</div>' if message else ''}
    <section class="stats">
      {_stat("Записи", counts["records"])}
      {_stat("Блокноты", counts["notebooks"])}
      {_stat("Оценки", counts["assessments"])}
      {_stat("Заполнения", counts["fills"])}
    </section>
    <div class="top-actions">
      <form method="post" action="/delete/all" onsubmit="return confirm('Удалить все загруженные данные и файлы?')">
        <button class="danger" type="submit">Удалить всё</button>
      </form>
    </div>
    {_records_table(records)}
    {_notebooks_table(notebooks)}
    {_fills_table(fills)}
    {_assessments_table(assessments)}
  </main>
</body>
</html>
"""


def _stat(label: str, value: int) -> str:
    return f'<div class="stat"><span class="muted">{escape(label)}</span><strong>{value}</strong></div>'


def _records_table(records: list[InterviewRecord]) -> str:
    rows = []
    for item in records:
        rows.append(
            "<tr>"
            f"<td>#{item.id}</td>"
            f"<td>{escape(str(item.user_id))}</td>"
            f"<td>{escape(item.file_type)}</td>"
            f"<td>{_file_cell(item.file_path)}</td>"
            f"<td>{len(item.transcript or '')}</td>"
            f"<td>{_dt(item.created_at)}</td>"
            f"<td>{_delete_button(f'/delete/record/{item.id}', 'Удалить')}</td>"
            "</tr>"
        )
    return _table(
        "Записи и транскрипты",
        ["ID", "User ID", "Тип", "Файл", "Длина текста", "Создано", ""],
        rows,
    )


def _notebooks_table(notebooks: list[ObserverNotebook]) -> str:
    rows = []
    for item in notebooks:
        rows.append(
            "<tr>"
            f"<td>#{item.id}</td>"
            f"<td>{escape(str(item.user_id))}</td>"
            f"<td>{escape(item.file_name or '')}</td>"
            f"<td>{_file_cell(item.file_path)}</td>"
            f"<td>{_dt(item.created_at)}</td>"
            f"<td>{_delete_button(f'/delete/notebook/{item.id}', 'Удалить')}</td>"
            "</tr>"
        )
    return _table("Блокноты наблюдателя", ["ID", "User ID", "Имя файла", "Файл", "Создано", ""], rows)


def _fills_table(fills: list[NotebookFillResult]) -> str:
    rows = []
    for item in fills:
        rows.append(
            "<tr>"
            f"<td>#{item.id}</td>"
            f"<td>Запись #{item.record_id}<br>Блокнот #{item.notebook_id}</td>"
            f"<td>{_file_cell(item.output_path)}</td>"
            f"<td>{_dt(item.created_at)}</td>"
            f"<td>{_delete_button(f'/delete/fill/{item.id}', 'Удалить')}</td>"
            "</tr>"
        )
    return _table("Заполненные блокноты", ["ID", "Связи", "Файл", "Создано", ""], rows)


def _assessments_table(assessments: list[AssessmentResult]) -> str:
    rows = []
    for item in assessments:
        rows.append(
            "<tr>"
            f"<td>#{item.id}</td>"
            f"<td>Запись #{item.record_id}</td>"
            f"<td>{escape((item.summary or '')[:240])}</td>"
            f"<td>{_dt(item.created_at)}</td>"
            f"<td>{_delete_button(f'/delete/assessment/{item.id}', 'Удалить')}</td>"
            "</tr>"
        )
    return _table("Оценки компетенций", ["ID", "Запись", "Summary", "Создано", ""], rows)


def _table(title: str, headers: list[str], rows: list[str]) -> str:
    body = "".join(rows) if rows else f"<tr><td colspan='{len(headers)}' class='muted'>Нет данных</td></tr>"
    head = "".join(f"<th>{escape(header)}</th>" for header in headers)
    return f"<h2>{escape(title)}</h2><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _delete_button(action: str, label: str) -> str:
    return (
        f'<form method="post" action="{escape(action)}" '
        'onsubmit="return confirm(\'Удалить выбранный объект?\')">'
        f'<button class="danger" type="submit">{escape(label)}</button></form>'
    )


def _file_cell(path: str | None) -> str:
    if not path:
        return "<span class='muted'>нет файла</span>"
    file_path = _resolve_runtime_path(path)
    exists = file_path.exists()
    size = _format_size(file_path.stat().st_size) if exists else "нет на диске"
    return f"<code>{escape(str(path))}</code><br><span class='muted'>{size}</span>"


def _format_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _dt(value: Any) -> str:
    return escape(value.strftime("%Y-%m-%d %H:%M") if value else "")


def _redirect(message: str) -> RedirectResponse:
    return RedirectResponse(url=f"/?message={quote(message)}", status_code=303)


def _safe_unlink(path: str | None) -> None:
    if not path:
        return
    file_path = _resolve_runtime_path(path)
    data_root = (Path.cwd() / "data").resolve()
    try:
        file_path.relative_to(data_root)
    except ValueError:
        return
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


def _resolve_runtime_path(path: str) -> Path:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    return file_path.resolve()


def _delete_empty_runtime_dirs() -> None:
    for dirname in ("uploads", "reports"):
        directory = Path.cwd() / "data" / dirname
        if directory.exists():
            for child in directory.iterdir():
                if child.is_file():
                    child.unlink()
