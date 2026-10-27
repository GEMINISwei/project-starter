"""一組 module manifest 的驗證規則 (`shared/module.py`): 撞名一律在組裝時就擋下。"""

import pytest
from fastapi import APIRouter
from sqlalchemy import MetaData
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.table import BaseTable
from shared.module import ModuleManifest, table_models, validate_modules


def test_table_models_are_stably_sorted():
    class ZetaTable(BaseTable):
        __tablename__ = "zeta_test"

    class AlphaTable(BaseTable):
        __tablename__ = "alpha_test"

    modules = (ModuleManifest("example", tables=(ZetaTable, AlphaTable)),)
    assert table_models(modules) == [AlphaTable, ZetaTable]


def test_validate_modules_rejects_duplicate_module_names():
    with pytest.raises(RuntimeError, match="duplicate module name"):
        validate_modules((ModuleManifest("same"), ModuleManifest("same")))


def test_validate_modules_rejects_duplicate_router_prefixes():
    with pytest.raises(RuntimeError, match="duplicate router prefix"):
        validate_modules(
            (
                ModuleManifest("one", routers=(APIRouter(prefix="/same"),)),
                ModuleManifest("two", routers=(APIRouter(prefix="/same"),)),
            )
        )


def test_validate_modules_rejects_duplicate_table_names():
    class FirstTable(BaseTable):
        __tablename__ = "duplicate_test"
        label: Mapped[str] = mapped_column(default="")

    # 同一個 `__tablename__` 在同一份 metadata 上會直接撞名, 所以第二個要換一份 metadata
    # 才建得起來 —— 這裡要驗的是 `validate_modules` 的檢查, 不是 SQLAlchemy 的檢查。
    class SecondBase(BaseTable):
        __abstract__ = True
        metadata = MetaData()

    class SecondTable(SecondBase):
        __tablename__ = "duplicate_test"
        label: Mapped[str] = mapped_column(default="")

    with pytest.raises(RuntimeError, match="duplicate table name"):
        validate_modules(
            (
                ModuleManifest("one", tables=(FirstTable,)),
                ModuleManifest("two", tables=(SecondTable,)),
            )
        )


def test_validate_modules_rejects_duplicate_table_classes():
    class SharedTable(BaseTable):
        __tablename__ = "shared_table_test"

    with pytest.raises(RuntimeError, match="duplicate table class"):
        validate_modules(
            (
                ModuleManifest("one", tables=(SharedTable,)),
                ModuleManifest("two", tables=(SharedTable,)),
            )
        )
