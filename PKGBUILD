# maintainer: ysg
pkgname=diskface
pkgver=3.8
pkgrel=1
pkgdesc="disk usage analyzer with live sorted results"
arch=('any')
url="https://github.com/harryeffinpotter/diskface"
license=('MIT')
depends=('python' 'python-rich')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel')
source=("$pkgname-$pkgver.tar.gz::$url/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
    cd "$pkgname-$pkgver"
    python -m build --wheel --no-isolation
}

package() {
    cd "$pkgname-$pkgver"
    python -m installer --destdir="$pkgdir" dist/*.whl
}
