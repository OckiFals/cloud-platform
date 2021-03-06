from django.http import Http404, QueryDict
from rest_framework import status
from rest_framework.response import Response
from rest_framework_mongoengine.generics import ListAPIView, GenericAPIView
from authenticate.authentication import JSONWebTokenAuthentication
from authenticate.permissions import IsUser
from nodes.models import Nodes
from supernodes.models import Supernodes
from nodes.serializers import NodeSerializer
from nodes.forms import NodePublishResetForm, NodeDuplicateForm

from cloud_platform.helpers import is_objectid_valid, is_url_regex_match


class NodesList(ListAPIView):
    """
    Retrieve  Nodes instance.
    Every nodes has visibility option: public and private.

    Usage:
    /nodes/                => retrieve all authenticated user nodes
    /nodes/?role=public    => retrieve authenticated user public nodes
    /nodes/?role=private   => retrieve authenticated user private nodes
    /nodes/?role=global    => retrieve all public nodes from other users
    /supernodes/:id/nodes/ => retrieve all specific supernode nodes
    """
    authentication_classes = (JSONWebTokenAuthentication,)
    permission_classes = (IsUser,)
    serializer_class = NodeSerializer

    @staticmethod
    def get_nodes(user, supernode=None, role=None):
        if supernode:
            if not role:
                return Nodes.objects.filter(user=user, supernode=supernode)
            else:
                if 'global' == role:
                    return Nodes.objects.filter(user__ne=user, supernode=supernode, is_public=1)
                elif 'public' == role:
                    return Nodes.objects.filter(user=user, supernode=supernode, is_public=1)
                else:  # private
                    return Nodes.objects.filter(user=user, supernode=supernode, is_public=0)
        if not role:
            return Nodes.objects.filter(user=user)
        else:
            if 'global' == role:
                return Nodes.objects.filter(user__ne=user, is_public=1)
            elif 'public' == role:
                return Nodes.objects.filter(user=user, is_public=1)
            else:  # private
                return Nodes.objects.filter(user=user, is_public=0)

    def get(self, request, *args, **kwargs):
        # check if request came from supernodes urls
        if is_url_regex_match(r'^/supernodes/(?P<pk>\w+)/nodes/', request.get_full_path()):
            if not is_objectid_valid(kwargs.get('pk')):
                return Response({
                    'detail': '%s is not valid ObjectId.' % kwargs.get('pk')
                }, status=status.HTTP_400_BAD_REQUEST)
            queryset = self.filter_queryset(
                self.get_nodes(request.user, kwargs.get('pk'), request.GET.get('role'))
            )
        else:
            queryset = self.filter_queryset(self.get_nodes(user=request.user, role=request.GET.get('role')))
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = NodeSerializer(page, many=True, context={'request': request})
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @staticmethod
    def post(request):
        if isinstance(request.data, QueryDict):
            return Response({
                'detail': 'Payload cannot be empty.'
            }, status=status.HTTP_400_BAD_REQUEST)
        supernode = Supernodes()
        # SlugRelatedField, avoid 'query does not matching' exception on non valid data payload
        if request.data.get('supernode'):
            supernode = Supernodes.objects.filter(user=request.user, label=request.data.get('supernode'))
            if not supernode:
                return Response({
                    'supernode': ['This field must be valid supernode label.']
                }, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({
                'supernode': ['This field is required.']
            }, status=status.HTTP_400_BAD_REQUEST)
        request.data.update({'user': request.user.username})
        serializer = NodeSerializer(data=request.data, context={'request': request, 'supernode': supernode[0]})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NodeDetail(GenericAPIView):
    """
    Retrieve, update or delete a Nodes instance.
    """
    authentication_classes = (JSONWebTokenAuthentication,)
    permission_classes = (IsUser,)

    @staticmethod
    def get_object(pk):
        try:
            return Nodes.objects.get(pk=pk)
        except Exception:
            raise Http404

    def get(self, request, pk, format=None):
        if not is_objectid_valid(pk):
            return Response({
                'detail': '%s is not valid ObjectId.' % pk
            }, status=status.HTTP_400_BAD_REQUEST)
        node = self.get_object(pk)
        if request.user != node.user and 0 == node.is_public:
            return Response({
                'detail': 'Not found.'
            }, status=status.HTTP_404_NOT_FOUND)
        serializer = NodeSerializer(node, context={'request': request})
        return Response(serializer.data)

    def put(self, request, pk, format=None):
        if not is_objectid_valid(pk):
            return Response({
                'detail': '%s is not valid ObjectId.' % pk
            }, status=status.HTTP_400_BAD_REQUEST)
        node = self.get_object(pk)
        if request.user != node.user:
            return Response({
                'detail': 'You can not update another person node.'
            }, status=status.HTTP_403_FORBIDDEN)

        # SlugRelatedField, avoid 'query does not matching' exception on non valid data payload
        if request.data.get('user'):
            request.data.pop('user')
        if request.data.get('supernode'):
            request.data.pop('supernode')

        serializer = NodeSerializer(node, data=request.data, context={'request': request}, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, format=None):
        if not is_objectid_valid(pk):
            return Response({
                'detail': '%s is not valid ObjectId.' % pk
            }, status=status.HTTP_400_BAD_REQUEST)
        node = self.get_object(pk)
        if request.user != node.user:
            return Response({
                'detail': 'You can not delete another person node.'
            }, status=status.HTTP_403_FORBIDDEN)
        node.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NodePublishReset(GenericAPIView):
    """
      Reset node publish per day remaining to publish per day initial value.
    """
    authentication_classes = (JSONWebTokenAuthentication,)
    permission_classes = (IsUser,)

    @staticmethod
    def get_object(pk):
        try:
            return Nodes.objects.get(pk=pk)
        except Exception:
            raise Http404

    def post(self, request):
        form = NodePublishResetForm(request.data)
        if form.is_valid():
            node = self.get_object(form.cleaned_data.get('id'))
            if request.user != node.user:
                return Response({
                    'detail': 'You can not reset  pubsperdayremain of another person node.'
                }, status=status.HTTP_403_FORBIDDEN)
            elif -1 == node.pubsperdayremain:
                return Response({
                    'detail': 'You only can not reset node with unlimited pubsperday'
                }, status=status.HTTP_400_BAD_REQUEST)
            node.pubsperdayremain = node.pubsperday
            node.save()
            serializer = NodeSerializer(node, context={'request': request})
            return Response(serializer.data)
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)


class NodeDuplicate(GenericAPIView):
    authentication_classes = (JSONWebTokenAuthentication,)
    permission_classes = (IsUser,)

    @staticmethod
    def get_object(pk):
        try:
            return Nodes.objects.get(pk=pk)
        except Exception:
            raise Http404

    def post(self, request):
        form = NodeDuplicateForm(request.data)
        if form.is_valid():
            node = self.get_object(form.cleaned_data.get('id'))
            if request.user != node.user:
                return Response({
                    'detail': 'You can not duplicate another person node.'
                }, status=status.HTTP_403_FORBIDDEN)
            bulk_insert = []
            for i in range(form.cleaned_data.get('count')):
                bulk_insert.append(Nodes(
                    user=request.user,
                    supernode=node.supernode,
                    label=node.label + '_' + str(i+1),
                    secretkey=node.secretkey,
                    is_public=node.is_public,
                    pubsperday=node.pubsperday,
                    pubsperdayremain=node.pubsperday
                ))
            Nodes.objects.insert(bulk_insert)
            return Response(
                {"results": ("%d duplicate has successfully added." % len(bulk_insert))},
                status=status.HTTP_201_CREATED
            )
        return Response(form.errors, status=status.HTTP_400_BAD_REQUEST)