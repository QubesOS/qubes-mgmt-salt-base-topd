%{!?version: %define version %(make get-version)}
%{!?rel: %define rel %(make get-release)}
%{!?package_name: %define package_name %(make get-package_name)}
%{!?package_summary: %define package_summary %(make get-summary)}
%{!?package_description: %define package_description %(make get-description)}

%{!?formula_name: %define formula_name %(make get-formula_name)}
%{!?state_name: %define state_name %(make get-state_name)}
%{!?saltenv: %define saltenv %(make get-saltenv)}
%{!?state_dir: %define state_dir %(make get-salt_state_dir)}
%{!?pillar_dir: %define pillar_dir %(make get-pillar_dir)}
%{!?formula_dir: %define formula_dir %(make get-formula_dir)}

Name:      qubes-mgmt-salt-base-topd
Version:   %{version}
Release:   %{rel}%{?dist}
Summary:   %{package_summary}
License:   GPL 2.0
URL:	   http://www.qubes-os.org/

Group:     System administration tools
BuildArch: noarch
Requires:  salt
Requires:  salt-minion
Requires:  qubes-mgmt-salt-config
Requires(post): /usr/bin/salt-call

%define _builddir %(pwd)

%description
%{package_description}

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
qubesctl saltutil.clear_cache -l quiet --out quiet > /dev/null || true
qubesctl saltutil.sync_all refresh=true -l quiet --out quiet > /dev/null || true

# Enable States
/usr/bin/salt-call --local topd.enable %{state_name} saltenv=%{saltenv} -l quiet --out quiet > /dev/null || true

# Enable Pillars
/usr/bin/salt-call --local topd.enable %{state_name}.config saltenv=%{saltenv} pillar=true -l quiet --out quiet > /dev/null || true

%files
%defattr(-,root,root)
%attr(750, root, root) %dir /srv/salt/_modules
/srv/salt/_modules/topd.py*

%attr(750, root, root) %dir /srv/salt/topd
/srv/salt/topd/init.conf
/srv/salt/topd/init.sls
/srv/salt/topd/init.top
/srv/salt/topd/LICENSE
/srv/salt/topd/README.rst

%attr(750, root, root) %dir /srv/salt/_utils
/srv/salt/_utils/adapt.py*
/srv/salt/_utils/fileinfo.py*
/srv/salt/_utils/matcher.py*
/srv/salt/_utils/pathinfo.py*
/srv/salt/_utils/pathutils.py*
/srv/salt/_utils/toputils.py*

%config(noreplace) /srv/pillar/topd/config.sls
/srv/pillar/topd/config.top

%changelog
