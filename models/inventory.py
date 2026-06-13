from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from database import Base


class InventoryUnit(str, enum.Enum):
    UNIT = "יחידות"
    KG = "קג"
    GRAM = "גרם"
    LITER = "ליטר"
    ML = "מל"
    PACK = "אריזות"


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    barcode = Column(String, index=True)
    category = Column(String, default="כללי")
    quantity = Column(Float, default=0)
    unit = Column(Enum(InventoryUnit), default=InventoryUnit.UNIT)
    min_quantity = Column(Float, default=1)
    location = Column(String, default="מטבח")

    added_by = Column(Integer, ForeignKey("users.id"))
    added_by_user = relationship("User", back_populates="inventory_items")

    expiry_date = Column(DateTime(timezone=True))
    last_purchased = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    on_shopping_list = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)


class ShoppingListItem(Base):
    __tablename__ = "shopping_list"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    quantity = Column(Float, default=1)
    unit = Column(Enum(InventoryUnit), default=InventoryUnit.UNIT)
    category = Column(String, default="כללי")
    is_checked = Column(Boolean, default=False)
    inventory_item_id = Column(Integer, ForeignKey("inventory_items.id"), nullable=True)
    added_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
