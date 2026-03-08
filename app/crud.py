from sqlalchemy.orm import Session
from .models import Link
from .utils import generate_short_code
from datetime import datetime


def create_link(db: Session, url: str, custom_alias=None, expires_at=None):

    short = custom_alias if custom_alias else generate_short_code()

    link = Link(
        original_url=url,
        short_code=short,
        expires_at=expires_at
    )

    db.add(link)
    db.commit()
    db.refresh(link)

    return link


def get_link(db: Session, short_code: str):
    return db.query(Link).filter(Link.short_code == short_code).first()


def delete_link(db: Session, short_code: str):

    link = get_link(db, short_code)

    if link:
        db.delete(link)
        db.commit()


def update_link(db: Session, short_code: str, new_url: str):

    link = get_link(db, short_code)

    link.original_url = new_url

    db.commit()

    return link


def search_by_url(db: Session, url: str):

    return db.query(Link).filter(Link.original_url == url).first()