"""证据数据访问类"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.entity.evidence_entity import EvidenceEntity
from db.repository.base_repository import BaseRepository
from model.evidence import Evidence

class EvidenceRepository(BaseRepository[EvidenceEntity, Evidence]):
    """证据数据访问类"""

    def __init__(self, session: Session):
        super().__init__(session, EvidenceEntity, Evidence)
        
    def get_by_script_id(self, script_id: int) -> Sequence[EvidenceEntity]:
        """根据剧本ID获取证据列表"""
        stmt = select(EvidenceEntity).where(EvidenceEntity.script_id == script_id)
        return self.session.execute(stmt).scalars().all()