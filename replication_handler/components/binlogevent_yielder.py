# -*- coding: utf-8 -*-
from collections import namedtuple
import logging

from pymysqlreplication import BinLogStreamReader
from pymysqlreplication.event import GtidEvent
from pymysqlreplication.event import QueryEvent
from pymysqlreplication.row_event import RowsEvent
from pymysqlreplication.row_event import UpdateRowsEvent
from pymysqlreplication.row_event import WriteRowsEvent

from replication_handler import config
from replication_handler.components.auto_position_gtid_finder import AutoPositionGtidFinder


log = logging.getLogger('replication_handler.components.binlogevent_yielder')

ReplicationHandlerEvent = namedtuple(
    'ReplicationHandlerEvent',
    ('event', 'gtid')
)


class BinlogEventYielder(object):

    def __init__(self):
        """Pull the default configuration and build a yielder from
           python-mysql-replication library.
           server_id doesn't seem to matter but must be set.
           blocking=True will keep this iterator infinite.
        """
        source_config = config.source_database_config.entries[0]
        repl_mysql_config = {
            'host': source_config['host'],
            'port': source_config['port'],
            'user': source_config['user'],
            'passwd': source_config['passwd']
        }

        self.stream = BinLogStreamReader(
            connection_settings=repl_mysql_config,
            server_id=1,
            blocking=True,
            only_events=[GtidEvent, QueryEvent, WriteRowsEvent, UpdateRowsEvent],
            auto_position=AutoPositionGtidFinder().get_gtid()
        )

        self.current_gtid = None

    def __iter__(self):
        return self

    def next(self):
        # It seems GtidEvent always appear before QueryEvent or RowsEvent.
        # Note that for RowsEvent, it will have one QueryEvent with query
        # "BEGIN" before the actual event to signal trasaction has begun.
        # have to use isinstance
        event = self.stream.fetchone()
        if isinstance(event, GtidEvent):
            self.current_gtid = event.gtid
            return self.next()
        elif isinstance(event, QueryEvent):
            if event.query == "BEGIN":
                return self.next()
            else:
                return ReplicationHandlerEvent(
                    gtid=self.current_gtid,
                    event=event
                )
        elif isinstance(event, RowsEvent):
            return ReplicationHandlerEvent(
                gtid=self.current_gtid,
                event=event
            )
        else:
            log.error("Encountered ignored event, event_type: {0}".format(
                event.event_type
            ))
