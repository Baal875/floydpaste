# main.py
import uuid
from datetime import datetime
import os

import databases
import sqlalchemy
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# --- setup FastAPI + templates ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- database config (Railway provides DATABASE_URL) ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set (add a PostgreSQL plugin in Railway)")

database = databases.Database(DATABASE_URL)
metadata = sqlalchemy.MetaData()

# --- define the `pastes` table ---
pastes = sqlalchemy.Table(
    "pastes",
    metadata,
    sqlalchemy.Column("id",        sqlalchemy.String,    primary_key=True),
    sqlalchemy.Column("content",   sqlalchemy.Text,      nullable=False),
    sqlalchemy.Column("title",     sqlalchemy.String,    nullable=False),
    sqlalchemy.Column("syntax",    sqlalchemy.String,    nullable=False, default="none"),
    sqlalchemy.Column("expires",   sqlalchemy.String,    nullable=False, default="never"),
    sqlalchemy.Column("visibility",sqlalchemy.String,    nullable=False, default="public"),
    sqlalchemy.Column("created_at",sqlalchemy.DateTime,  nullable=False, default=datetime.utcnow),
)

# create tables on startup
engine = sqlalchemy.create_engine(DATABASE_URL)
metadata.create_all(engine)


@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


# --- serve the home page ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --- create a new paste ---
@app.post("/api/paste")
async def create_paste(
    content: str      = Form(...),
    title: str        = Form("Untitled Paste"),
    syntax: str       = Form("none"),
    expires: str      = Form("never"),
    visibility: str   = Form("public")
):
    paste_id = uuid.uuid4().hex[:8]
    now = datetime.utcnow()

    query = pastes.insert().values(
        id=paste_id,
        content=content,
        title=title,
        syntax=syntax,
        expires=expires,
        visibility=visibility,
        created_at=now
    )
    await database.execute(query)
    return {"url": f"/paste/{paste_id}"}


# --- list top pastes by content length ---
@app.get("/api/top")
async def top_pastes():
    query = (
        sqlalchemy.select([pastes.c.id, pastes.c.title])
        .order_by(sqlalchemy.func.length(pastes.c.content).desc())
        .limit(10)
    )
    rows = await database.fetch_all(query)
    return [{"id": r["id"], "title": r["title"]} for r in rows]


# --- view a paste ---
@app.get("/paste/{paste_id}", response_class=HTMLResponse)
async def view_paste(request: Request, paste_id: str):
    query = sqlalchemy.select([pastes]).where(pastes.c.id == paste_id)
    row = await database.fetch_one(query)
    if not row:
        raise HTTPException(status_code=404, detail="Paste not found")

    return templates.TemplateResponse("paste.html", {
        "request":  request,
        "paste_id": row["id"],
        "title":    row["title"],
        "content":  row["content"],
        "syntax":   row["syntax"],
        "expires":  row["expires"],
        "visibility": row["visibility"],
        "created_at": row["created_at"],
    })


# --- list most recent pastes ---
@app.get("/api/recent")
async def recent_pastes():
    query = (
        sqlalchemy.select([pastes.c.id, pastes.c.title])
        .order_by(pastes.c.created_at.desc())
        .limit(10)
    )
    rows = await database.fetch_all(query)
    return [{"id": r["id"], "title": r["title"]} for r in rows]


# --- simple healthcheck ---
@app.get("/ping")
async def ping():
    return {"status": "alive"}


def start():
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    start()
