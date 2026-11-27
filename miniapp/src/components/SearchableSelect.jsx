import { useCallback, useEffect, useRef, useState } from "react";

export function SearchableSelect({ value, options, onChange, placeholder = "Select..." }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef(null);
  const searchRef = useRef(null);
  const filteredOptions = options.filter((option) =>
    option.label.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const selectedOption = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) return undefined;
    const closeOnOutsideClick = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    searchRef.current?.focus();
    return () => document.removeEventListener("pointerdown", closeOnOutsideClick);
  }, [open]);

  const openMenu = () => {
    setQuery("");
    setActiveIndex(Math.max(0, options.findIndex((option) => option.value === value)));
    setOpen(true);
  };

  const chooseOption = (option) => {
    onChange(option.value);
    setOpen(false);
    setQuery("");
  };

  const handleSearchKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setOpen(false);
    } else if (event.key === "ArrowDown" && filteredOptions.length) {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % filteredOptions.length);
    } else if (event.key === "ArrowUp" && filteredOptions.length) {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + filteredOptions.length) % filteredOptions.length);
    } else if (event.key === "Enter" && filteredOptions[activeIndex]) {
      event.preventDefault();
      chooseOption(filteredOptions[activeIndex]);
    }
  };

  return (
    <div className="searchable-select" ref={containerRef}>
      <button
        className="searchable-select-trigger"
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => (open ? setOpen(false) : openMenu())}
      >
        <span className={!selectedOption ? "select-placeholder" : ""}>
          {selectedOption?.label || placeholder}
        </span>
        <span className="select-chevron" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="searchable-select-menu">
          <input
            ref={searchRef}
            className="searchable-select-search"
            type="search"
            role="searchbox"
            aria-label="Search options"
            placeholder="Type to search..."
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleSearchKeyDown}
          />
          <div className="searchable-select-options" role="listbox">
            {filteredOptions.map((option, index) => (
              <button
                className={`searchable-select-option ${option.value === value ? "selected" : ""} ${index === activeIndex ? "active" : ""}`}
                key={option.value}
                type="button"
                role="option"
                aria-selected={option.value === value}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => chooseOption(option)}
              >
                {option.label}
              </button>
            ))}
            {!filteredOptions.length && (
              <p className="searchable-select-empty">No matching options.</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
