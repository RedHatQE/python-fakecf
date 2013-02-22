Name:		python-fakecf
Version:	0.2
Release:	1%{?dist}
Summary:	Python library to emulate CloudForamtion stuff when it is not accessible

Group:		Development/Python
License:	GPLv3+
URL:		https://github.com/RedHatQE/python-fakecf
Source0:	%{name}-%{version}.tar.gz
BuildRoot:	%(mktemp -ud %{_tmppath}/%{name}-%{version}-%{release}-XXXXXX)
BuildArch:  noarch

BuildRequires:	python-devel
Requires:	python-boto

%description
Python library to emulate CloudForamtion stuff when it is not accessible.

%prep
%setup -q

%build

%install
%{__python} setup.py install -O1 --root $RPM_BUILD_ROOT

%clean
rm -rf $RPM_BUILD_ROOT

%files
%defattr(-,root,root,-)
%{python_sitelib}/*.egg-info
%{python_sitelib}/fakecf

%changelog
* Fri Feb 22 2013 Vitaly Kuznetsov <vitty@redhat.com> 0.2-1
- new package built with tito


