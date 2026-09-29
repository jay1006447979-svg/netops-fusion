"""笔记 API — 笔记的增删改查 + 按标题/内容搜索"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from app.db.base import get_session
from app.db.models import Note

router = APIRouter(prefix="/api/notes", tags=["笔记"])


class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    content: str = ""


class NoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=256)
    content: str | None = None


def _note_dict(n: Note, with_content: bool = True) -> dict:
    d = {
        "id": n.id,
        "title": n.title,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }
    if with_content:
        d["content"] = n.content
    return d


@router.get("")
async def list_notes(keyword: str | None = None):
    """获取笔记列表 — 可选 keyword 参数，按标题或内容模糊搜索"""
    async with get_session() as session:
        stmt = select(Note)
        if keyword and keyword.strip():
            kw = f"%{keyword.strip()}%"
            stmt = stmt.where(or_(Note.title.like(kw), Note.content.like(kw)))
        stmt = stmt.order_by(Note.updated_at.desc())
        result = await session.execute(stmt)
        notes = result.scalars().all()
        return {
            "success": True,
            "total": len(notes),
            "keyword": keyword or "",
            "notes": [_note_dict(n) for n in notes],
        }


@router.post("")
async def create_note(req: NoteCreate):
    """新建笔记"""
    async with get_session() as session:
        note = Note(title=req.title.strip(), content=req.content or "")
        session.add(note)
        await session.flush()
        return {"success": True, "note_id": note.id, "note": _note_dict(note)}


@router.get("/{note_id}")
async def get_note(note_id: str):
    """获取单条笔记详情"""
    async with get_session() as session:
        note = await session.get(Note, note_id)
        if not note:
            raise HTTPException(404, "笔记不存在")
        return {"success": True, "note": _note_dict(note)}


@router.put("/{note_id}")
async def update_note(note_id: str, req: NoteUpdate):
    """更新笔记"""
    async with get_session() as session:
        note = await session.get(Note, note_id)
        if not note:
            raise HTTPException(404, "笔记不存在")
        data = req.model_dump(exclude_unset=True)
        if not data:
            raise HTTPException(400, "没有需要更新的字段")
        if "title" in data:
            note.title = data["title"].strip()
        if "content" in data and data["content"] is not None:
            note.content = data["content"]
        return {"success": True, "note": _note_dict(note)}


@router.delete("/{note_id}")
async def delete_note(note_id: str):
    """删除笔记"""
    async with get_session() as session:
        note = await session.get(Note, note_id)
        if not note:
            raise HTTPException(404, "笔记不存在")
        await session.delete(note)
        return {"success": True}
