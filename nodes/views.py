from django.http import Http404
from django.shortcuts import render
from rest_framework.response import Response
from rest_framework.views import APIView
from nodes.models import Nodes
from nodes.serializers import NodeSerializer


class NodesList(APIView):
    @staticmethod
    def get(request, format=None):
        nodes = Nodes.objects.all()
        serializer = NodeSerializer(nodes, many=True, context={'request': request})
        return Response(serializer.data)


class NodeDetail(APIView):
    """
    Retrieve, update or delete a Nodes instance.
    """

    @staticmethod
    def get_object(pk):
        try:
            return Nodes.objects.get(pk=pk)
        except Nodes.DoesNotExist:
            raise Http404

    def get(self, request, pk, format=None):
        node = self.get_object(pk)
        serializer = NodeSerializer(node, context={'request': request})
        return Response(serializer.data)