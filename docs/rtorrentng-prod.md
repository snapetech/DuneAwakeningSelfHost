# rtorrentNG Production Notes

`kspls0` runs `rtorrentng-prod.service` as a host systemd service. Keep the
container root filesystem read-only so accidental writes cannot fill the NVMe
Docker/containerd layer.

Install the production drop-in:

```sh
sudo mkdir -p /etc/systemd/system/rtorrentng-prod.service.d
sudo install -m 0644 config/systemd/rtorrentng-prod-readonly-datapool.conf \
  /etc/systemd/system/rtorrentng-prod.service.d/readonly-datapool.conf
sudo systemctl daemon-reload
sudo systemctl restart rtorrentng-prod.service
```

The drop-in requires `/mnt/datapool_lvm_media` to be mounted before the service
can start. Torrent data, app state, rTorrent scratch config, and logs are all
bound to persistent storage:

- `/downloads` -> `/mnt/datapool_lvm_media`
- `/data` -> `/mnt/datapool_lvm_media/download/temp`
- `/var/lib/rtorrentng` -> `/mnt/datapool_lvm_media/rtorrentng-prod-data`
- `/var/lib/torrentng` -> `/mnt/datapool_lvm_media/rtorrentng-prod-data/torrentng`
- `/var/log/rtorrent` -> `/mnt/datapool_lvm_media/rtorrentng-prod-data/log/rtorrent`
- `/etc/rtorrent` -> `/mnt/datapool_lvm_media/rtorrentng-prod-data/etc-rtorrent`

`/config` stays read-only and contains the host-managed production config from
`/etc/rtorrentng-prod`. UI-managed rTorrent settings must not rewrite that file.
They are written to the separate overlay selected by:

```text
TNG_RTORRENT_OVERLAY=/etc/rtorrent/tng-ui-overlay.rc
```

The production `/etc/rtorrentng-prod/rtorrent.rc` must import that overlay after
site defaults:

```text
# TorrentNG UI-managed overlay. Keep production defaults above this line.
import = /etc/rtorrent/tng-ui-overlay.rc
```

Verification:

```sh
systemctl is-active rtorrentng-prod.service
systemctl is-enabled rtorrentng-prod.service
docker ps -a --filter name=rtorrentng-prod --format '{{.Names}}\t{{.Status}}\t{{.Size}}'
docker inspect rtorrentng-prod --format 'ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}}'
curl -sS -o /dev/null -w 'http=%{http_code}\n' http://127.0.0.1:8082/
```

Expected results: service active/enabled, `ReadonlyRootfs=true`, HTTP 200, and a
small writable container layer.
