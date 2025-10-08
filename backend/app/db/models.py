from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    content_type = Column(String, index=True)
    original_path = Column(String)
    aggregated_text = Column(Text, nullable=True)
    status = Column(String, default="uploaded", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    chunks = relationship("Chunk", back_populates="document", cascade="all,delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page = Column(Integer, default=0)
    position = Column(Integer, default=0)
    text = Column(Text)
    embedding_distance = Column(Float, nullable=True)
    document = relationship("Document", back_populates="chunks")
