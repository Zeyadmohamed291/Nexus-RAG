from typing import List, Optional, Union
from sqlalchemy.future import select
from .BaseDataModel import BaseDataModel
from .db_schemes import Asset


class AssetModel(BaseDataModel):
    """
    Data access layer for uploaded files and document assets.
    """

    def __init__(self, db_client: object) -> None:
        super().__init__(db_client=db_client)
        self.db_client = db_client

    @classmethod
    async def create_instance(cls, db_client: object) -> "AssetModel":
        return cls(db_client)

    async def create_asset(self, asset: Asset) -> Asset:
        """Persist a new file asset to the database."""
        async with self.db_client() as session:
            async with session.begin():
                session.add(asset)
            await session.refresh(asset)
        return asset

    async def get_all_project_assets(
        self,
        asset_project_id: Union[int, str],
        asset_type: str
    ) -> List[Asset]:
        """Retrieve all assets associated with a project of a specific type."""
        async with self.db_client() as session:
            stmt = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_type == asset_type
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_asset_record(
        self,
        asset_project_id: Union[int, str],
        asset_name: str
    ) -> Optional[Asset]:
        """Fetch an asset by project ID and unique file asset name."""
        async with self.db_client() as session:
            stmt = select(Asset).where(
                Asset.asset_project_id == asset_project_id,
                Asset.asset_name == asset_name
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
