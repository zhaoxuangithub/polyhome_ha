import json
import datetime

class JSONEncoder(json.JSONEncoder):
    """JSONEncoder that supports Home Assistant objects."""

    # pylint: disable=method-hidden
    def default(self, o):
        """Convert Home Assistant objects.
        Hand other objects to the original method.
        """
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, set):
            return list(o)
        elif hasattr(o, 'as_dict'):
            return o.as_dict()

        try:
            return json.JSONEncoder.default(self, o)
        except TypeError:
            # If the JSON serializer couldn't serialize it
            # it might be a generator, convert it to a list
            try:
                return [self.default(child_obj)
                        for child_obj in o]
            except TypeError:
                # Ok, we're lost, cause the original error
                return json.JSONEncoder.default(self, o)