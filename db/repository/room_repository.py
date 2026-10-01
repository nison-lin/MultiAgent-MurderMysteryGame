"""游戏房间数据访问类"""

from sqlalchemy.orm import Session

from db.entity.room_entity import RoomEntity, StatusEnum
from db.repository.base_repository import BaseRepository
from error.errors import DataError
from model.room import Room

class RoomRepository(BaseRepository[RoomEntity, Room]):
    """游戏房间数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, RoomEntity, Room)

    def get_in_progress(self) -> list[Room]:
        """获取进行中的游戏房间列表"""
        room_entities = self.session.query(RoomEntity).filter(RoomEntity.status == StatusEnum.IN_PROGRESS).all()
        if not room_entities:
            return []
        return [super()._to_model(room_entity) for room_entity in room_entities]

    def finish(self, room_id: int) -> bool:
        """将游戏房间标记为已结束"""
        room_entity = self.get_entity_by_id(room_id)
        if not room_entity:
            raise DataError("房间不存在")
        room_entity.status = StatusEnum.FINISHED
        self.session.flush()
        return True