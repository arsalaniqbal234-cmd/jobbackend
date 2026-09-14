from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.auth import current_user, verified_email
from database import get_db

router = APIRouter(prefix="/saved-searches", tags=["Saved Searches"])


@router.post("/", response_model=schemas.SavedSearchResponse)
def create_saved_search(search: schemas.SavedSearchCreate, db: Session = Depends(get_db),
                        user_id: str = Depends(current_user)):
    return crud.create_saved_search(db, search, user_id, verified_email(user_id))


@router.get("/", response_model=list[schemas.SavedSearchResponse])
def get_user_saved_searches(db: Session = Depends(get_db), user_id: str = Depends(current_user)):
    return crud.get_saved_searches_by_user(db, user_id)


@router.delete("/{search_id}", status_code=204)
def delete_saved_search(search_id: int, db: Session = Depends(get_db),
                        user_id: str = Depends(current_user)):
    if not crud.delete_saved_search(db, search_id, user_id):
        raise HTTPException(404, "Saved search not found")
