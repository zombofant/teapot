import unittest

from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
from sqlalchemy import *
from sqlalchemy.orm import *

__all__ = [
    "Base",
    "A",
    "B",
    "get_sessionmaker",
    "DBTestCase",
]

class Base(declarative_base()):
    __abstract__ = True

class A(Base):
    __tablename__ = "as"

    a_id = Column(Integer,
                  primary_key=True,
                  nullable=False)

    value1 = Column(Unicode(255), nullable=False)
    value2 = Column(Unicode(255), nullable=False)

class B(Base):
    __tablename__ = "bs"

    b_id = Column(Integer,
                  primary_key=True,
                  nullable=False)

    a_id = Column(Integer,
                  ForeignKey("as.a_id",
                             ondelete="CASCADE"),
                  nullable=False)

    valueb = Column(Unicode(255), nullable=False)

    a = relationship("A")

def get_sessionmaker():
    engine = create_engine(
        "sqlite:///:memory:",
        encoding="utf8",
        convert_unicode=True)

    Base.metadata.create_all(engine)
    return sessionmaker(
        bind=engine)

class DBTestCase(unittest.TestCase):
    def setUp(self):
        self.db = get_sessionmaker()()

    def insert_test_data(self):
        all_as = []
        all_bs = []

        a_s = []
        for v1, v2 in [
                ("foo", "bar"),
                ("bar", "baz"),
                ("fnord", "funk")]:
            a = A(value1=v1, value2=v2)
            if v1 != "fnord":
                a_s.append(a)
            all_as.append(a)
            self.db.add(a)
        self.db.commit()

        for a in a_s:
            value = "for A{}".format(a.a_id)
            b = B(a=a, valueb=value)
            self.db.add(b)
            all_bs.append(b)
        self.db.commit()

        return all_as, all_bs


    def tearDown(self):
        self.db.close()
