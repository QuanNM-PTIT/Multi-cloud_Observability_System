from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_serializer

from app.core.timezone import to_app_timezone


class TimezoneAwareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime(self, value):
        """Serialize datetime fields in the application timezone with an explicit offset."""
        if isinstance(value, datetime):
            return to_app_timezone(value).isoformat()
        return value
