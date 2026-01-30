"""Tests for ImmutableParameterizableMixin."""
import pytest
from mixinforge.mixins_and_metaclasses.immutable_parameterizable_mixin import ImmutableParameterizableMixin

class Point(ImmutableParameterizableMixin):
    """Concrete implementation for testing."""
    def __init__(self, x: int, y: int):
        super().__init__()
        self.x = x
        self.y = y

    def get_params(self):
        return {"x": self.x, "y": self.y}

class ColorPoint(Point):
    """Subclass to test type inequality."""
    pass

def test_equality_with_same_params():
    """Verify objects with identical parameters are equal."""
    p1 = Point(1, 2)
    p2 = Point(1, 2)
    
    assert p1 == p2
    assert p2 == p1

def test_inequality_with_different_params():
    """Verify objects with different parameters are not equal."""
    p1 = Point(1, 2)
    p2 = Point(1, 3)
    
    assert p1 != p2

def test_inequality_with_different_types():
    """Verify objects of different types are not equal even with same params."""
    p1 = Point(1, 2)
    p2 = ColorPoint(1, 2)
    
    # Even though params are same, types are different
    assert p1 != p2
    assert p2 != p1

def test_equality_with_other_types():
    """Verify inequality with completely different types."""
    p = Point(1, 2)
    assert p is not None
    assert p != "string"
    assert p != 123
    assert p != object()

def test_hashing_consistency():
    """Verify hash is consistent with equality."""
    p1 = Point(1, 2)
    p2 = Point(1, 2)
    p3 = Point(3, 4)
    
    assert hash(p1) == hash(p2)
    assert hash(p1) != hash(p3)
    
    # Verify hash stability
    assert hash(p1) == hash(p1)

def test_hash_fails_during_initialization():
    """Verify hashing raises RuntimeError if called before init finishes."""
    class PrematureHasher(ImmutableParameterizableMixin):
        def __init__(self):
            super().__init__()
            # Accessing hash before init is done
            hash(self)

        def get_params(self):
            return {}

    with pytest.raises(RuntimeError, match="Cannot get identity key of uninitialized object"):
        PrematureHasher()

def test_initialization_guard_compliance():
    """Verify that setting _init_finished=True prematurely triggers GuardedInitMeta error."""
    # GuardedInitMeta auto-injects _init_finished=False before __init__ runs,
    # but if __init__ sets it to True prematurely, an error is raised.

    class BadInit(ImmutableParameterizableMixin):
        def __init__(self):
            super().__init__()
            self._init_finished = True  # Prematurely set to True

        def get_params(self):
            return {}

    with pytest.raises(RuntimeError, match="must not set _init_finished to True"):
        BadInit()

def test_param_retrieval():
    """Verify get_jsparams works as expected (base functionality)."""
    p = Point(10, 20)
    # Just ensuring inheritance works
    assert p.get_params() == {"x": 10, "y": 20}
