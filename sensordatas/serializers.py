from collections import OrderedDict

from datetime import datetime
from rest_framework import serializers
from rest_framework.fields import ListField, CharField
from rest_framework.reverse import reverse
from rest_framework_mongoengine.serializers import DocumentSerializer
from sensordatas.models import Sensordatas
from supernodes.models import Supernodes
from nodes.models import Nodes

from cloud_platform.helpers import is_objectid_valid


class SensordataSerializer(DocumentSerializer):
    supernode = serializers.SlugRelatedField(slug_field="label", queryset=Supernodes.objects)
    node = serializers.SlugRelatedField(slug_field="label", queryset=Nodes.objects, required=False)
    # extra field
    testing = serializers.BooleanField(required=False)
    url = serializers.SerializerMethodField()
    nodeurl = serializers.SerializerMethodField(method_name='getnodeurl')
    sensorurl = serializers.SerializerMethodField(method_name='getsensorurl')
    sensorlabel = serializers.SerializerMethodField(method_name='getsensorlabel')

    class Meta:
        model = Sensordatas
        fields = '__all__'

    def get_url(self, obj):
        return reverse('sensordata-detail', args=[obj.id], request=self.context['request'])

    def getnodeurl(self, obj):
        if obj.node:
            return reverse('nodes-detail', args=[obj.node.pk], request=self.context['request'])
        return None

    def getsensorurl(self, obj):
        _obj = obj.node if obj.node else obj.supernode
        return reverse('node-sensor-detail', args=[_obj.pk, str(obj.sensor)], request=self.context['request'])

    @staticmethod
    def getsensorlabel(obj):
        if obj.node:
            return obj.node.sensors.get(id=obj.sensor).label
        else:
            return obj.supernode.sensors.get(id=obj.sensor).label

    def validate(self, data):
        super(SensordataSerializer, self).validate(data)
        node = data.get('node')

        # TODO supernode publish limit?
        if not node:
            return data

        ''' -1 means node has not publish limit '''
        if -1 is node.pubsperday:
            return data

        ''' check if node has remaining publish this day '''
        if 0 != node.pubsperdayremain:
            return data
        raise serializers.ValidationError('publish is limit.')

    def create(self, validated_data):
        supernode = validated_data.get('supernode')
        node = validated_data.get('node')
        sensor = validated_data.get('sensor')

        ''' create new pubcription instance '''
        pub = Sensordatas()
        pub.supernode = supernode
        if node:
            pub.node = node
        pub.sensor = sensor
        pub.timestamp = validated_data.get('timestamp')
        pub.data = validated_data.get('data')
        if not validated_data.get('testing'):
            pub.save()
        return pub


class SensordataFormatSerializer(DocumentSerializer):
    label = CharField()
    sensors = ListField(required=False)
    nodes = ListField(required=False)
    testing = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Sensordatas
        fields = ('label', 'sensors', 'nodes', 'testing')

    @staticmethod
    def get_node(supenodeid, nodeid):
        try:
            return Nodes.objects.get(supernode=supenodeid, id=nodeid)
        except Nodes.DoesNotExist:
            return False

    @staticmethod
    def get_node_sensor(nodesensors, sensorlabel):
        try:
            return nodesensors.get(label=sensorlabel)
        except Exception:
            return False

    def validate(self, attrs):
        super(SensordataFormatSerializer, self).validate(attrs=attrs)
        supernode = self.context.get('request').user
        node = Nodes()
        errors = OrderedDict()
        # node sensors
        nodeiderror = []
        nodeformaterror = []
        nodesensorerror = []

        '''
        validate format from sensors[i]
        publish sensordata captured from supernode sensors
        '''
        sensorerror = self.supernode_sensors_validate(supernode, attrs.get('sensors'))

        '''validate format from nodes[i]'''
        for index, nodes in enumerate(attrs.get('nodes')):
            if not nodes.get('id'):
                nodeiderror.append(
                    "node[%d].id: This field may not be null." % index
                )
            else:
                if not is_objectid_valid(nodes.get('id')):
                    nodeiderror.append(
                        "node[%d].id: %s is not valid ObjectId." % (index, nodes.get('id'))
                    )
                    continue
                else:
                    node = self.get_node(supernode.id, nodes.get('id'))
                    if not node:
                        nodeiderror.append(
                            "node[%d].id: Object with label=%s does not exist.." % (index, nodes.get('id'))
                        )
                        continue

            if not nodes.get('format'):
                nodeformaterror.append(
                    "node[%d].format: This field may not be null." % index
                )
            else:
                if not isinstance(nodes.get('format'), list):
                    nodeformaterror.append(
                        "node[%d].format: Expected a list." % index
                    )
                else:
                    if 2 != len(nodes.get('format')) or \
                            ('data' != nodes.get('format')[0] or 'timestamp' != nodes.get('format')[1]):
                        nodeformaterror.append(
                            "node[%d].format: Expected format ['data', 'timestamp']." % index
                        )

            if not nodes.get('sensors'):
                nodesensorerror.append(
                    "node[%d].sensors: This field may not be null." % index
                )
            else:
                if not isinstance(nodes.get('sensors'), list):
                    nodesensorerror.append(
                        "node[%d].sensors: Expected a list." % index
                    )
                else:
                    _sensorerror = self.nodes_sensors_validate(index, node, nodes.get('sensors'))
                    if _sensorerror:
                        nodesensorerror.append(_sensorerror)
        else:
            if sensorerror:
                errors['supernode'] = {'sensors': sensorerror}
            if nodeiderror:
                errors['node'] = {'id': nodeiderror}
            if nodeformaterror:
                errors['node'] = {'format': nodeformaterror}
            if nodesensorerror:
                errors['node'] = {'sensors': nodesensorerror}

        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    '''
    helper method: validate format of node[i].sensors
    '''

    def nodes_sensors_validate(self, index, node, sensors):
        sensorerror = []
        for jindex, sensor in enumerate(sensors):
            if not isinstance(sensor, dict):
                sensorerror.append(
                    "node[%d].sensors[%d]: Expected a dict." % (index, jindex)
                )

            if not sensor.get('label'):
                sensorerror.append(
                    "node[%d].sensors[%d].label: This field may not be null." % (index, jindex)
                )
            else:
                if not self.get_node_sensor(node.sensors, sensor.get('label')):
                    sensorerror.append(
                        "node[%d].sensors[%d].label: Object with label=%s does not exist.."
                        % (index, jindex, sensor.get('label'))
                    )

            if not sensor.get('value'):
                sensorerror.append(
                    "node[%d].sensors[%d].value: This field may not be null." % (index, jindex)
                )
            else:
                if not isinstance(sensor.get('value'), list):
                    sensorerror.append(
                        "node[%d].sensors[%d].value: Expected a list of int." %
                        (index, jindex)
                    )
                else:
                    for kindex, values in enumerate(sensor.get('value')):
                        if (not isinstance(values[0], int) and not isinstance(values[0], float)) \
                                or not isinstance(values[1], int) and not isinstance(values[1], float):
                            sensorerror.append(
                                "node[%d].sensors[%d].value[%d]: Expected list of int or float." %
                                (index, jindex, kindex)
                            )
        if sensorerror:
            return sensorerror
        else:
            return None

    '''
    helper method: validate format of supernode sensors
    '''

    def supernode_sensors_validate(self, supernode, sensors):
        sensorerror = []
        for jindex, sensor in enumerate(sensors):
            if not isinstance(sensor, dict):
                sensorerror.append(
                    "sensors[%d]: Expected a dict." % jindex
                )

            if not sensor.get('label'):
                sensorerror.append(
                    "sensors[%d].label: This field may not be null." % jindex
                )
            else:
                if not self.get_node_sensor(supernode.sensors, sensor.get('label')):
                    sensorerror.append(
                        "sensors[%d].label: Object with label=%s does not exist.."
                        % (jindex, sensor.get('label'))
                    )

            if not sensor.get('value'):
                sensorerror.append(
                    "sensors[%d].value: This field may not be null." % jindex
                )
            else:
                if not isinstance(sensor.get('value'), list):
                    sensorerror.append(
                        "sensors[%d].value: Expected a list of int." %
                        jindex
                    )
                else:
                    for kindex, values in enumerate(sensor.get('value')):
                        if (not isinstance(values[0], int) and not isinstance(values[0], float)) \
                                or not isinstance(values[1], int) and not isinstance(values[1], float):
                            sensorerror.append(
                                "sensors[%d].value[%d]: Expected list of int or float." %
                                (jindex, kindex)
                            )
        if sensorerror:
            return sensorerror
        else:
            return None

    @staticmethod
    def timestamp_validate(timestamp):
        try:
            return datetime.fromtimestamp(timestamp)
        except ValueError:
            return datetime.fromtimestamp(timestamp/1000)

    def create(self, validated_data):
        supernode = self.context.get('request').user
        supernode_sensors = validated_data.get('sensors')
        supernode_nodes = validated_data.get('nodes')
        istesting = validated_data.get('testing')
        count = 0

        # save data from supernode sensors
        for sensor in supernode_sensors:
            sensor_obj = supernode.sensors.get(label=sensor.get('label'))
            for value in sensor.get('value'):
                timestamp = self.timestamp_validate(value[1])
                data = {'supernode': supernode.label, 'sensor': sensor_obj.id,
                        'data': value[0], 'timestamp': timestamp, 'testing': istesting}
                serializer = SensordataSerializer(data=data)
                if serializer.is_valid():
                    count += 1
                    serializer.save()
                else:
                    raise serializers.ValidationError(serializer.errors)
            if not istesting:
                # TODO supernode publish limit?
                ''' decrement Supernodes pubsperdayremain when node has publish limit '''

        # save data from node sensors
        for node in supernode_nodes:
            node_obj = self.get_node(supernode.id, node.get('id'))
            for sensor in node.get('sensors'):
                sensor_obj = node_obj.sensors.get(label=sensor.get('label'))
                for value in sensor.get('value'):
                    timestamp = datetime.fromtimestamp(value[1])
                    data = {'supernode': supernode.label, 'node': node_obj.label, 'sensor': sensor_obj.id,
                            'data': value[0], 'timestamp': timestamp, 'testing': istesting}
                    serializer = SensordataSerializer(data=data)
                    if serializer.is_valid():
                        count += 1
                        serializer.save()
                    else:
                        raise serializers.ValidationError(serializer.errors)
                if not istesting:
                    ''' decrement Nodes pubsperdayremain when node has publish limit '''
                    if -1 is not node_obj.pubsperday:
                        node_obj.pubsperdayremain -= 1
                        node_obj.save()
        if 0 != count:
            return "%d sensordatas has successfully added." % count
        else:
            return "No sensordatas added."
