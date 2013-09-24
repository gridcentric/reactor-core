import time
import threading
import uuid
import traceback

from reactor.zookeeper.objects import DatalessObject
from reactor.zookeeper.objects import JSONObject
from reactor.objects.instance import Instances
from reactor.zookeeper.cache import Cache

from connection import DockerEndpointConfig

# Existing containers (all systems).
CONTAINERS = "containers"

# Scheduled containers (pending).
TO_START = "scheduling"

# Starting containers (locks).
STARTING = "starting"

# Scheduling info (free slots).
SCHEDULER_INFO = "hosts"

class Docker(DatalessObject):

    def containers(self):
        return self._get_child(CONTAINERS, clazz=Instances)

    def to_start(self):
        return self._get_child(TO_START, clazz=Instances)

    def starting(self):
        return self._get_child(STARTING, clazz=Instances)

    def scheduler_info(self):
        return self._get_child(SCHEDULER_INFO, clazz=Instances)

# We stuff this key in the environment to specially
# recognize reactor containers, and perform accounting
# based on their configured "slots" on a restart.
SLOTS_ENVIRONMENT_KEY = '_REACTOR_SCHEDULER_SLOTS'

class DockerManager(object):

    def __init__(self, zkobj, this_ip, config, register_ip):
        super(DockerManager, self).__init__()
        self.this_ip = this_ip
        self.zkobj = zkobj and zkobj._cast_as(Docker)
        self.config = config
        self.uuid = str(uuid.uuid4())
        self.used_slots = 0
        self.scheduler_cache = {}
        self.image_cond = threading.Condition()
        self.images = {}

        self._containers = Cache(self.zkobj.containers(), update=self._delete)
        self._to_start = Cache(self.zkobj.to_start(), update=self._start)
        self._starting = self.zkobj.starting()
        self._scheduler_info = Cache(self.zkobj.scheduler_info(), update=self._notify_scheduler)

        self._load()
        self._update_scheduler_info()

    def break_refs(self):
        self.zkobj.unwatch()
        if hasattr(self, '_containers'):
            self._scheduler_info.remove(self.uuid)
            del self._containers
            del self._to_start
            del self._starting
            del self._scheduler_info

    def _extract_ip(self, instance_id):
        try:
            # Extract the private port.
            instance_info = self.config.client().inspect_container(instance_id)
            network_info = instance_info["NetworkSettings"]
            if network_info != None and network_info.get("PortMapping"):
                tcp_ports = network_info["PortMapping"].get("Tcp")
                if tcp_ports and len(tcp_ports) > 0:
                    private_port = tcp_ports.items()[0][1]
                    return '%s:%s' % (self.this_ip, private_port)
        except Exception:
            traceback.print_exc()

        # No port available.
        # Unfortunately this means this isn't
        # a running instance and we will kill it.
        return None

    def _load(self):
        # Check that our instances match expectations.
        for instance_id in map(lambda x: x['Id'][:12],
                self.config.client().containers(all=True)):

            # Is it one of ours?
            try:
                instance_info = self.config.client().inspect_container(instance_id)
            except Exception:
                traceback.print_exc()
                continue

            env = instance_info['Config']['Env']
            if env != None:
                env = dict(map(lambda x: x.split("=", 1), env))
                if SLOTS_ENVIRONMENT_KEY in env:
                    if instance_id in self._containers.list():
                        # NOTE: We update the IP here as well because it
                        # may have changed if this was a reboot event or
                        # something similar.
                        ip_address = self._extract_ip(instance_id)
                        self.used_slots += int(env[SLOTS_ENVIRONMENT_KEY])
                        if ip_address:
                            # Reset the IP address in the store.
                            self._containers.add(
                                instance_id, ip_address, mustexist=True)
                    else:
                        # No need to do any accounting here.
                        self.config.client().kill(instance_id)
                        self.config.client().remove_container(instance_id)

        # Clean out non-running instances.
        # NOTE: This duplicates a lot of the functionality
        # above, but it's important to ensure that we get
        # the accounting correct.
        self._delete()

    def _notify_scheduler(self):
        # Update scheduler information. Either a new
        # instance has been started, or a new server
        # has come online, or some combination.
        if hasattr(self, '_scheduler_info'):
            self.scheduler_cache = self._scheduler_info.as_map()

            # We've changed scheduler info, so we'd best
            # rerun our schedule() function and ensure that
            # everything gets scheduled.
            self._start()

    def _update_scheduler_info(self):
        # Update our scheduler information.
        # NOTE: This will generate _notify_scheduler()
        # asynchronously, so there's no need to call it.
        self._scheduler_info.add(self.uuid,
            (self.used_slots, self.config.slots), ephemeral=True)

    def instances(self):
        # Clean up all the dead containers.
        # We don't care about failure here, as
        # this is just a best effort call.
        try:
            self._delete()
        except Exception:
            pass

        # List the aggregate of all servers.
        return self._containers.as_map()

    def start(self, config, timeout=10.0, params=None):
        # Submit a scheduling request.
        # We do so by writing the uuid to
        # a unique node in the to_start pool.
        # This will be picked up by the a
        # server that thinks it has the most
        # (relative) slots available.
        start = time.time()
        this_uuid = str(uuid.uuid4())

        # Serialize the configuration.
        # This installs an ephermal node in Zookeeper
        # (basically as an RPC entry) which will fire
        # appropriately when it is changed.
        self._to_start.add(this_uuid, config._values(), ephemeral=True)
        ref = self._to_start._get_child(this_uuid, clazz=JSONObject)
        try:
            cond = threading.Condition()
            def _notify(value):
                cond.acquire()
                cond.notifyAll()
                cond.release()

            cond.acquire()
            instance_info = ref._get_data(watch=_notify)
            try:
                while True:
                    # Check if we're set.
                    # This is a pretty loose system for
                    # RPC, where we know the result is either
                    # a tuple (the result), an exception (str)
                    # or the original dictionary configuration.
                    if isinstance(instance_info, str):
                        # Shit, an exception on the other end.
                        raise Exception(instance_info)
                    elif isinstance(instance_info, dict):
                        # Still our configuration, waiting.
                        pass
                    else:
                        # Successfully spawned.
                        return instance_info

                    # Check if we're out of time.
                    now = time.time()
                    if now >= start + timeout:
                        break

                    # Wait for a notification and refresh.
                    cond.wait(start + timeout - now)
                    instance_info = ref._get_data()
            finally:
                cond.release()
        finally:
            ref.unwatch()
            ref._delete()

        # No success.
        raise Exception("timed out")

    def _spawn(self, config):
        # Ensure that this image is available.
        self._pull(config.image)

        # Figure out the right port.
        # NOTE: This is derived from the endpoint.
        if config.port():
            # This is weird, but they require a str.
            ports = [str(config.port())]
        else:
            ports = None

        # Add the slots to the environment.
        env = config.get_environment()
        env[SLOTS_ENVIRONMENT_KEY] = config.slots

        # Create the container.
        instance_info = self.config.client().create_container(
            config.image,
            config.command,
            hostname=config.hostname or None,
            user=config.user or None,
            detach=True,
            stdin_open=False,
            tty=False,
            mem_limit=config.mem_limit or None,
            ports=ports,
            environment=env,
            dns=config.dns or None,
            privileged=False)

        # Grab the id to work with here.
        instance_id = instance_info['Id'][:12]

        # Start the container.
        self.config.client().start(instance_id)

        # Grab the local IP for mapping.
        ip_address = self._extract_ip(instance_id)

        # Off to the races.
        return (instance_id, config.slots, ip_address)

    def _pull(self, image):
        self.image_cond.acquire()
        try:
            # Wait while pending.
            while self.images.has_key(image) and \
                not self.images[image]:
                self.image_cond.wait()

            # Start the request.
            self.images[image] = False
            self.config.client().pull(image)

            # Success.
            self.images[image] = True
        except Exception:
            del self.images[image]
            raise
        finally:
            self.image_cond.notifyAll()
            self.image_cond.release()

    def _start(self, clean_uuid=None):
        # Check for an early notification.
        if not hasattr(self, '_to_start'):
            return

        # Read all instances waiting to be scheduled.
        for (this_uuid, config) in self._to_start.as_map().items():

            # This is a result or something else.
            # Will eventually be pruned (ephemeral)
            # or removed by the caller.
            if not isinstance(config, dict):
                continue

            # Get the config.
            # FIXME: This is currently a hack that is required to
            # break the circular reference between the manager and
            # the connection. If there is a reference, then neither
            # the manager nor the connection will ever be cleaned up.
            config = DockerEndpointConfig(values=config, section='cloud:docker')

            # Figure out if we should schedule this one.
            # We do this by figuring out which host will
            # have the least slot used by *percentage*
            # after the process is completed.
            min_used = 1.0
            best_hosts = []
            for (host_uuid, (used_slots, total_slots)) in self.scheduler_cache.items():
                this_used = float(used_slots + config.slots) / total_slots
                if this_used < min_used:
                    min_used = this_used
                    best_hosts = [host_uuid]
                elif this_used == min_used:
                    best_hosts.append(host_uuid)

            # Are we a candidate?
            if self.uuid in best_hosts:
                if self._starting.lock([this_uuid]):
                    try:
                        # First, do the actual launch and update
                        # our scheduling information so people can
                        # make the right decisions.
                        (instance_id, slots, ip_address) = self._spawn(config)
                        self.used_slots += slots
                        self._update_scheduler_info()

                        # Finally add the container to the list of
                        # containers and return to the caller.
                        if self._to_start.add(this_uuid,
                            (instance_id, ip_address), mustexist=True):
                            self._containers.add(instance_id, ip_address)

                    except Exception, e:
                        # Write the result out as an exception.
                        self._to_start.add(this_uuid, (str(e),), mustexist=True)
                    finally:
                        # Always clear the lock.
                        self._starting.remove(this_uuid)

    def delete(self, instance_id):
        if instance_id in self._containers.list():
            # Remove from the list of containers.
            # This will eventually be picked up by the
            # owner and the container will be killed.
            self._containers.remove(instance_id)

    def _delete(self):
        for instance_id in map(lambda x: x['Id'][:12],
                self.config.client().containers(all=True)):

            try:
                instance_info = self.config.client().inspect_container(instance_id)
            except Exception:
                traceback.print_exc()
                continue

            env = instance_info['Config']['Env']
            running = instance_info['State']['Running']
            if env != None:
                env = dict(map(lambda x: x.split("=", 1), env))
                if SLOTS_ENVIRONMENT_KEY in env:
                    if not instance_id in self._containers.list():
                        # No longer with us, kill the container.
                        try:
                            self.config.client().kill(instance_id)
                            self.config.client().remove_container(instance_id)
                        except Exception:
                            traceback.print_exc()
                            continue
                        self.used_slots -= int(env[SLOTS_ENVIRONMENT_KEY])
                    elif not running:
                        # Not a live container anymore, remove it.
                        # This will result in the core dropping it.
                        self._containers.remove(instance_id)
