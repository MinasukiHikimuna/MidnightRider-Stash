from abc import ABC, abstractmethod


class StashboxClient(ABC):
    @abstractmethod
    def query_performer_image(self, performer_stash_id):
        pass

    @abstractmethod
    def query_studio_image(self, performer_stash_id):
        pass

    @abstractmethod
    def query_scenes(self, performer_stash_id):
        pass
