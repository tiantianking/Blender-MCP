class PrevizError(RuntimeError):
    """Base error returned safely to callers."""


class ValidationError(PrevizError):
    pass


class UnsupportedFeature(PrevizError):
    pass


class EntityNotFound(PrevizError):
    pass


class AmbiguousEntity(PrevizError):
    pass

