from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from datetime import datetime

from .database import Base, engine, get_db
from . import models, crud, schemas
from .cache import get_cache, set_cache, delete_cache

Base.metadata.create_all(bind=engine)

app = FastAPI(title="URL Shortener API")


@app.post("/links/shorten")
def create_link(link: schemas.LinkCreate, db: Session = Depends(get_db)):

    existing = crud.search_by_url(db, link.original_url)

    if existing:
        return existing

    created = crud.create_link(
        db,
        link.original_url,
        link.custom_alias,
        link.expires_at
    )

    return created


@app.get("/{short_code}")
def redirect(short_code: str, db: Session = Depends(get_db)):

    cached = get_cache(short_code)

    if cached:
        return RedirectResponse(cached)

    link = crud.get_link(db, short_code)

    if not link:
        raise HTTPException(404)

    if link.expires_at and link.expires_at < datetime.utcnow():
        raise HTTPException(410)

    link.clicks += 1
    link.last_used = datetime.utcnow()

    db.commit()

    set_cache(short_code, link.original_url)

    return RedirectResponse(link.original_url)


@app.delete("/links/{short_code}")
def delete_link(short_code: str, db: Session = Depends(get_db)):

    crud.delete_link(db, short_code)

    delete_cache(short_code)

    return {"status": "deleted"}


@app.put("/links/{short_code}")
def update_link(short_code: str, link: schemas.LinkUpdate, db: Session = Depends(get_db)):

    updated = crud.update_link(db, short_code, link.original_url)

    delete_cache(short_code)

    return updated


@app.get("/links/{short_code}/stats")
def stats(short_code: str, db: Session = Depends(get_db)):

    link = crud.get_link(db, short_code)

    if not link:
        raise HTTPException(404)

    return {
        "original_url": link.original_url,
        "created_at": link.created_at,
        "clicks": link.clicks,
        "last_used": link.last_used
    }


@app.get("/links/search")
def search(original_url: str, db: Session = Depends(get_db)):

    link = crud.search_by_url(db, original_url)

    if not link:
        raise HTTPException(404)

    return link