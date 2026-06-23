class CustomSelect {
    constructor(el, options = {}) {
        if (!el || el.tagName !== 'SELECT') return;
        this.select = el;
        this.options = options;
        this._build();
        this._bind();
    }

    get value() {
        return this._hiddenInput.value;
    }

    set value(val) {
        this._setValue(val);
    }

    _build() {
        this.select.style.display = 'none';

        this.wrapper = document.createElement('div');
        this.wrapper.className = 'custom-select';

        this.trigger = document.createElement('button');
        this.trigger.type = 'button';
        this.trigger.className = 'custom-select-trigger';
        this.trigger.setAttribute('aria-haspopup', 'listbox');
        this.trigger.setAttribute('aria-expanded', 'false');
        if (this.select.disabled) {
            this.trigger.disabled = true;
        }

        this.valueEl = document.createElement('span');
        this.valueEl.className = 'custom-select-value';

        this.arrowEl = document.createElement('i');
        this.arrowEl.className = 'fa-solid fa-chevron-down custom-select-arrow';

        this.trigger.appendChild(this.valueEl);
        this.trigger.appendChild(this.arrowEl);

        this.menu = document.createElement('div');
        this.menu.className = 'custom-select-menu';
        this.menu.setAttribute('role', 'listbox');

        this._hiddenInput = document.createElement('input');
        this._hiddenInput.type = 'hidden';
        this._hiddenInput.name = this.select.name || '';
        this.select.removeAttribute('name');

        this._items = [];
        this._populateItems();

        const parent = this.select.parentNode;
        parent.insertBefore(this.wrapper, this.select);
        this.wrapper.appendChild(this.trigger);
        this.wrapper.appendChild(this.menu);
        this.wrapper.appendChild(this._hiddenInput);
    }

    _populateItems() {
        this.menu.innerHTML = '';
        this._items = [];
        const options = Array.from(this.select.options);

        options.forEach((opt, i) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'custom-select-item';
            item.textContent = opt.text;
            item.dataset.value = opt.value;
            item.dataset.index = i;
            item.setAttribute('role', 'option');

            if (opt.selected) {
                item.classList.add('selected');
                this.valueEl.textContent = opt.text;
                this._hiddenInput.value = opt.value;
            }

            this.menu.appendChild(item);
            this._items.push(item);
        });
    }

    _bind() {
        this.trigger.addEventListener('click', (e) => {
            if (this.select.disabled) return;
            e.stopPropagation();
            this.toggle();
        });

        this._items.forEach((item) => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                this._selectItem(item);
                this.close();
            });
        });

        document.addEventListener('click', () => {
            this.close();
        });

        document.addEventListener('keydown', (e) => {
            if (!this.menu.classList.contains('open')) return;

            const currentIndex = this._items.findIndex(el => el.classList.contains('selected'));
            let newIndex = currentIndex;

            switch (e.key) {
                case 'ArrowDown':
                    e.preventDefault();
                    newIndex = Math.min(currentIndex + 1, this._items.length - 1);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    newIndex = Math.max(currentIndex - 1, 0);
                    break;
                case 'Enter':
                    e.preventDefault();
                    if (currentIndex >= 0) {
                        this._selectItem(this._items[currentIndex]);
                        this.close();
                    }
                    return;
                case 'Escape':
                    e.preventDefault();
                    this.close();
                    return;
                default:
                    return;
            }

            if (newIndex !== currentIndex && this._items[newIndex]) {
                this._items[newIndex].focus();
                this._items.forEach(el => el.classList.remove('selected'));
                this._items[newIndex].classList.add('selected');
                this.valueEl.textContent = this._items[newIndex].textContent;
                this._hiddenInput.value = this._items[newIndex].dataset.value;
                this._items[newIndex].scrollIntoView({ block: 'nearest' });
            }
        });
    }

    _selectItem(item) {
        this._items.forEach(el => el.classList.remove('selected'));
        item.classList.add('selected');
        this.valueEl.textContent = item.textContent;
        this._hiddenInput.value = item.dataset.value;

        this.select.value = item.dataset.value;
        this.select.dispatchEvent(new Event('change', { bubbles: true }));

        if (this.options.onChange) {
            this.options.onChange(item.dataset.value, item.textContent);
        }
    }

    _setValue(val) {
        const item = this._items.find(el => el.dataset.value === String(val));
        if (item) {
            this._selectItem(item);
        }
    }

    open() {
        if (this.menu.classList.contains('open')) return;
        this.menu.classList.add('open');
        this.trigger.classList.add('open');
        this.trigger.setAttribute('aria-expanded', 'true');

        const selected = this._items.find(el => el.classList.contains('selected'));
        if (selected) {
            selected.scrollIntoView({ block: 'nearest' });
            selected.focus();
        }
    }

    close() {
        this.menu.classList.remove('open');
        this.trigger.classList.remove('open');
        this.trigger.setAttribute('aria-expanded', 'false');
    }

    toggle() {
        if (this.menu.classList.contains('open')) {
            this.close();
        } else {
            this.open();
        }
    }

    updateOptions(options) {
        this.select.innerHTML = '';
        options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.value;
            o.text = opt.text;
            if (opt.selected) o.selected = true;
            this.select.appendChild(o);
        });
        this._populateItems();
        this._rebindItems();
    }

    _rebindItems() {
        this._items.forEach((item) => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                this._selectItem(item);
                this.close();
            });
        });
    }

    static init(selector = '.custom-select-init') {
        document.querySelectorAll(selector).forEach(el => {
            if (!el._customSelect) {
                el._customSelect = new CustomSelect(el);
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    CustomSelect.init();
});
