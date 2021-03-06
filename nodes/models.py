from mongoengine.document import Document, EmbeddedDocument
from mongoengine import StringField, IntField, FloatField, ReferenceField, EmbeddedDocumentField, \
    EmbeddedDocumentListField, CASCADE
from sensors.models import Sensors
from users.models import User
from supernodes.models import Supernodes


class Coordinates(EmbeddedDocument):
    lat = FloatField(required=True, null=False)
    long = FloatField(required=True, null=False)

    def __unicode__(self):
        return str([self.lat, self.long])


class Nodes(Document):
    user = ReferenceField(User, reverse_delete_rule=CASCADE)
    supernode = ReferenceField(Supernodes, reverse_delete_rule=CASCADE)
    label = StringField(max_length=28)
    secretkey = StringField(required=True, max_length=16)
    is_public = IntField(default=0)
    pubsperday = IntField(default=0)
    pubsperdayremain = IntField(default=0)
    sensors = EmbeddedDocumentListField(document_type=Sensors)
    coordinates = EmbeddedDocumentField(document_type=Coordinates, required=False, null=True)
