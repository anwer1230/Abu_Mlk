import { Router, type IRouter } from "express";
import healthRouter from "./health";
import sharesRouter from "./shares";

const router: IRouter = Router();

router.use(healthRouter);
router.use(sharesRouter);

export default router;
