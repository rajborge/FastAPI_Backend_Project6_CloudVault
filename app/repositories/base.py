from typing import Generic,TypeVar,Type,cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

ModelType=TypeVar("ModelType")

class BaseRepository(Generic[ModelType]):
    def __init__(
            self,
            db:Session,
            model:Type[ModelType],
        ):
            self.db=db
            self.model=model

    def create(self,obj:ModelType)->ModelType:
        self.db.add(obj)
        return obj
    
    def get_by_id(
              self,
              id:UUID,
    )->ModelType | None:
        return cast(ModelType | None,self.db.get(self.model,id))
    
    def update(self,obj:ModelType)->ModelType:
         return obj
    
    def delete(self,obj:ModelType)->None:
         self.db.delete(obj)

