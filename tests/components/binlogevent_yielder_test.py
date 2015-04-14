# -*- coding: utf-8 -*-
from collections import namedtuple
from itertools import izip
import mock
import pytest

from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.event import GtidEvent
from pymysqlreplication.event import QueryEvent
from pymysqlreplication.row_event import WriteRowsEvent

from replication_handler.components.auto_position_gtid_finder import AutoPositionGtidFinder
from replication_handler.components.binlogevent_yielder import BinlogEventYielder
from replication_handler.components.binlogevent_yielder import IgnoredEventException
from replication_handler.components.binlogevent_yielder import ReplicationHandlerEvent


EventInfo = namedtuple(
    'EventInfo', ('event', 'call_count')
)


class TestBinlogEventYielder(object):

    @pytest.yield_fixture
    def patch_fetchone(self):
        with mock.patch.object(
            BinLogStreamReader,
            'fetchone',
        ) as mock_fetchone:
            yield mock_fetchone

    @pytest.yield_fixture
    def patch_get_gtid_to_resume_tailing_from(self):
        with mock.patch.object(
            AutoPositionGtidFinder,
            'get_gtid_to_resume_tailing_from',
        ) as mock_get_gtid_to_resume_tailing_from:
            mock_get_gtid_to_resume_tailing_from.return_value = None
            yield mock_get_gtid_to_resume_tailing_from

    def test_schema_event_next(self, patch_fetchone, patch_get_gtid_to_resume_tailing_from):
        gtid_event = mock.Mock(spec=GtidEvent)
        schema_event = mock.Mock(spec=QueryEvent)
        schema_event.query = "ALTER TABLE STATEMENT"
        replication_handler_event = ReplicationHandlerEvent(
            event=schema_event,
            gtid=gtid_event.gtid
        )
        patch_fetchone.side_effect = [
            gtid_event,
            schema_event
        ]
        binlog_event_yielder = BinlogEventYielder()
        for event in binlog_event_yielder:
            assert event == replication_handler_event
            assert patch_fetchone.call_count == 2

    def test_data_event_next(self, patch_fetchone, patch_get_gtid_to_resume_tailing_from):
        gtid_event = mock.Mock(spec=GtidEvent)
        query_event = mock.Mock(spec=QueryEvent)
        query_event.query = "BEGIN"
        data_event_1 = mock.Mock(spec=WriteRowsEvent)
        data_event_2 = mock.Mock(spec=WriteRowsEvent)
        patch_fetchone.side_effect = [
            gtid_event,
            query_event,
            data_event_1,
            data_event_2
        ]
        expected_event_info = self._build_expected_event_info(
            gtid_event,
            query_event,
            data_event_1,
            data_event_2
        )
        binlog_event_yielder = BinlogEventYielder()
        for event, expected_event_info in izip(
            binlog_event_yielder,
            expected_event_info
        ):
            assert event == expected_event_info.event
            assert patch_fetchone.call_count == expected_event_info.call_count

    def _build_expected_event_info(self, gtid_event, query_event, data_event_1, data_event_2):
        replication_handler_event_1 = ReplicationHandlerEvent(
            event=query_event,
            gtid=gtid_event.gtid
        )
        replication_handler_event_2 = ReplicationHandlerEvent(
            event=data_event_1,
            gtid=gtid_event.gtid
        )
        replication_handler_event_3 = ReplicationHandlerEvent(
            event=data_event_2,
            gtid=gtid_event.gtid
        )
        expected_event_info = [
            EventInfo(replication_handler_event_1, 2),
            EventInfo(replication_handler_event_2, 3),
            EventInfo(replication_handler_event_3, 4)
        ]
        return expected_event_info

    def test_ignored_event_type(self, patch_fetchone, patch_get_gtid_to_resume_tailing_from):
        ignored_event = mock.Mock()
        patch_fetchone.return_value = ignored_event
        with pytest.raises(IgnoredEventException):
            binlog_event_yielder = BinlogEventYielder()
            binlog_event_yielder.next()