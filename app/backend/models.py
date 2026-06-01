from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

Base = declarative_base()

class DeviceType(str, enum.Enum):
    router = "router"
    access_point = "access_point"

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    ip_address = Column(String, unique=True, index=True)
    mac_address = Column(String, unique=True, nullable=True)
    brand = Column(String, nullable=True)
    device_type = Column(Enum(DeviceType))
    ssh_user = Column(String)
    ssh_password = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
