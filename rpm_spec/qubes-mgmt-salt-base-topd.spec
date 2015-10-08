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
#/usr/bin/salt-call --local state.sls qubes.config -l quiet --out quiet > /dev/null || true
/usr/bin/salt-call --local saltutil.sync_all -l quiet --out quiet > /dev/null || true

# Enable States
/usr/bin/salt-call --local topd.enable %{state_name} saltenv=%{saltenv} -l quiet --out quiet > /dev/null || true

%files
%defattr(-,root,root)
%attr(750, root, root) %dir %{formula_dir}
%{formula_dir}/*
%attr(750, root, root) %dir %{state_dir}/_topd
%attr(750, root, root) %dir %{pillar_dir}/_topd

%changelog
