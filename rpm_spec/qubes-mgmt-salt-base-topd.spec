%{!?version: %define version %(cat version)}

Name:      qubes-mgmt-salt-base-topd
Version:   %{version}
Release:   1%{?dist}
Summary:   Salt top module plugin that allows top drop-ins
License:   GPL 2.0
URL:	   http://www.qubes-os.org/

Group:     System administration tools
BuildArch: noarch
Requires:  salt
Requires:  salt-minion
Requires:  qubes-mgmt-salt-config
Requires:  qubes-mgmt-salt-base-overrides
Requires:  qubes-mgmt-salt-base-overrides-libs
Requires(post): /usr/bin/salt-call

%define _builddir %(pwd)

%description
Salt top module plugin that allows top drop-ins

%prep
# we operate on the current directory, so no need to unpack anything
# symlink is to generate useful debuginfo packages
rm -f %{name}-%{version}
ln -sf . %{name}-%{version}
%setup -T -D

%build

%install
make install DESTDIR=%{buildroot} LIBDIR=%{_libdir} BINDIR=%{_bindir} SBINDIR=%{_sbindir} SYSCONFDIR=%{_sysconfdir}

%post
# Update Salt Configuration
salt-call --local saltutil.clear_cache -l quiet --out quiet > /dev/null || true
salt-call --local saltutil.sync_all refresh=true -l quiet --out quiet > /dev/null || true

# Enable States
/usr/bin/salt-call --local top.enable topd saltenv=base -l quiet --out quiet > /dev/null || true

# Enable Pillars
/usr/bin/salt-call --local top.enable topd.config saltenv=base pillar=true -l quiet --out quiet > /dev/null || true

%files
%defattr(-,root,root)
%doc LICENSE README.rst
%attr(750, root, root) %dir /srv/salt/_modules
/srv/salt/_modules/topd.py*

%attr(750, root, root) %dir /srv/salt/topd
/srv/salt/topd/init.conf
/srv/salt/topd/init.sls
/srv/salt/topd/init.top
/srv/salt/topd/LICENSE
/srv/salt/topd/README.rst

%attr(750, root, root) %dir /srv/salt/_utils
/srv/salt/_utils/fileinfo.py*
/srv/salt/_utils/matcher.py*
/srv/salt/_utils/pathinfo.py*
/srv/salt/_utils/pathutils.py*
/srv/salt/_utils/toputils.py*

%config(noreplace) /srv/pillar/topd/config.sls
/srv/pillar/topd/config.top

%changelog
