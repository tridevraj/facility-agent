from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import Base


def make_session_factory(url):
    kwargs = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
