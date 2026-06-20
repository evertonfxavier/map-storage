import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { FaHdd } from "react-icons/fa";
import { StoragePanel } from "./components";

export default definePlugin(() => ({
  name: "Map Storage",
  titleView: <div className={staticClasses.Title}>Map Storage</div>,
  content: <StoragePanel />,
  icon: <FaHdd />,
  onDismount() {
    console.log("Map Storage unloading");
  },
}));
