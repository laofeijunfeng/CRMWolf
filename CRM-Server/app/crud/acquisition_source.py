from sqlalchemy.orm import Session

from app.models.acquisition_source import AcquisitionSource
from app.services import acquisition_source_service


class AcquisitionSourceCRUD:
    def get_by_public_id(self, db: Session, public_id: str, team_id: int) -> AcquisitionSource | None:
        return acquisition_source_service.get_by_public_id(db, public_id, team_id)

    def list_options(
        self,
        db: Session,
        team_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[AcquisitionSource]:
        return acquisition_source_service.list_options(db, team_id, include_inactive=include_inactive)


acquisition_source_crud = AcquisitionSourceCRUD()
