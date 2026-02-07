from abc import ABC, abstractmethod


class StashboxClient(ABC):
    @abstractmethod
    def query_performer_image(self, performer_stash_id):
        pass

    @abstractmethod
    def query_studio_image(self, studio_stash_id):
        pass

    @abstractmethod
    def query_scenes(self, performer_stash_id):
        pass

    @abstractmethod
    def query_scenes_by_studio(self, studio_stash_ids: list[str]):
        pass

    @abstractmethod
    def query_scenes_by_tag(self, tag_id: str):
        pass

    @abstractmethod
    def find_studio_children(self, studio_stash_id: str) -> list[dict]:
        pass

    @abstractmethod
    def find_tag_id(self, tag_name: str) -> str | None:
        pass
