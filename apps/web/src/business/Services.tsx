import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Save, X } from "lucide-react";
import { api } from "../lib/api";
import { errorMessage, money } from "../lib/format";
import { Notice } from "../customer/ui";
import { AppFrame } from "./shell";

type Service = {
  id: string;
  name: string;
  description: string;
  category: string;
  pricing_model: "PER_ITEM" | "PER_KG" | "PACKAGE";
  price: number;
  turnaround_hours: number;
  sort_order: number;
  active: boolean;
};
const BLANK: Service = {
  id: "",
  name: "",
  description: "",
  category: "Wash & Iron",
  pricing_model: "PER_ITEM",
  price: 0,
  turnaround_hours: 24,
  sort_order: 0,
  active: true,
};
const CATEGORIES = ["Wash & Iron", "Wash & Fold", "Dry Cleaning", "Household"];

export default function Services() {
  const { t } = useTranslation();
  const [list, setList] = useState<Service[] | null>(null);
  const [editing, setEditing] = useState<Service | null>(null);
  const [error, setError] = useState("");

  const load = () =>
    api<Service[]>("/api/v1/business/services", { auth: "business" })
      .then(setList)
      .catch((e) => setError(errorMessage(e)));
  useEffect(() => {
    load();
  }, []);

  async function persist(s: Service) {
    const { id, ...body } = s;
    await api(`/api/v1/business/services${id ? `/${id}` : ""}`, {
      auth: "business",
      method: id ? "PUT" : "POST",
      body,
    });
  }

  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const next: Service = {
      ...editing!,
      name: String(fd.get("name")).trim(),
      description: String(fd.get("description") ?? ""),
      category: String(fd.get("category")),
      pricing_model: fd.get("model") as Service["pricing_model"],
      price: Number(fd.get("price")),
      turnaround_hours: Number(fd.get("turnaround")),
    };
    try {
      await persist(next);
      setEditing(null);
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  async function toggle(s: Service) {
    try {
      await persist({ ...s, active: !s.active });
      load();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <AppFrame
      title={t("biz.nav.services")}
      action={
        <button className="primary" onClick={() => setEditing({ ...BLANK })}>
          <Plus /> {t("biz.addService")}
        </button>
      }
    >
      <p className="dashSub">{t("biz.servicesIntro")}</p>
      {error && <Notice>{error}</Notice>}
      {editing && (
        <form className="inlineEditor" onSubmit={save}>
          <div className="spread">
            <h2>{editing.id ? t("biz.editService") : t("biz.addService")}</h2>
            <button
              type="button"
              className="iconBtn"
              aria-label={t("common.close")}
              onClick={() => setEditing(null)}
            >
              <X />
            </button>
          </div>
          <div className="fourFields">
            <label>
              {t("biz.serviceName")}
              <input
                name="name"
                required
                minLength={2}
                defaultValue={editing.name}
              />
            </label>
            <label>
              {t("biz.category")}
              <select name="category" defaultValue={editing.category}>
                {[...new Set([...CATEGORIES, editing.category])].map((c) => (
                  <option key={c} value={c}>
                    {t(`categories.${c}`, { defaultValue: c })}
                  </option>
                ))}
              </select>
            </label>
            <label>
              {t("biz.pricingModel")}
              <select name="model" defaultValue={editing.pricing_model}>
                <option value="PER_ITEM">{t("biz.perItem")}</option>
                <option value="PER_KG">{t("biz.perKg")}</option>
                <option value="PACKAGE">{t("biz.perPackage")}</option>
              </select>
            </label>
            <label>
              {t("biz.priceTzs")}
              <input
                name="price"
                required
                type="number"
                min="0"
                step="100"
                defaultValue={editing.price || ""}
              />
            </label>
            <label>
              {t("biz.turnaroundHours")}
              <input
                name="turnaround"
                required
                type="number"
                min="1"
                max="720"
                defaultValue={editing.turnaround_hours}
              />
            </label>
            <label>
              {t("biz.description")}
              <input
                name="description"
                maxLength={500}
                defaultValue={editing.description}
              />
            </label>
          </div>
          <button className="primary">
            <Save /> {t("biz.saveService")}
          </button>
        </form>
      )}
      <section className="serviceTable">
        <div className="tableHead serviceCols">
          <span>{t("biz.serviceName")}</span>
          <span>{t("biz.category")}</span>
          <span>{t("biz.turnaroundHours")}</span>
          <span>{t("biz.priceTzs")}</span>
          <span>{t("biz.active")}</span>
          <span />
        </div>
        {!list && <div className="tableLoading">{t("common.loading")}</div>}
        {list?.map((s) => (
          <div className="serviceRow serviceCols" key={s.id}>
            <b>{s.name}</b>
            <span>
              {t(`categories.${s.category}`, { defaultValue: s.category })}
            </span>
            <span>{s.turnaround_hours}h</span>
            <strong>
              {money(s.price)}
              {s.pricing_model !== "PER_ITEM" &&
                t(`walkin.unit.${s.pricing_model}`)}
            </strong>
            <button
              className={"toggle " + (s.active ? "on" : "")}
              role="switch"
              aria-checked={s.active}
              aria-label={t("biz.active")}
              onClick={() => toggle(s)}
            >
              <i />
            </button>
            <button className="textBtn" onClick={() => setEditing(s)}>
              {t("biz.edit")}
            </button>
          </div>
        ))}
      </section>
    </AppFrame>
  );
}
